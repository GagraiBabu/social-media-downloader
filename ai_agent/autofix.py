import json
import time
import requests

from .agent import agent
from .config import settings
from .diagnostics import diagnostics
from .github_tools import github
from .render_tools import render


def _json(text):
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI returned invalid JSON") from exc


def _safe(path):
    return isinstance(path, str) and path and not path.startswith("/") and ".." not in path.split("/") and not path.lower().endswith((".env", ".pem", ".key"))


def run_autofix(request, auto_apply=True):
    if settings.GITHUB_BRANCH == "main":
        raise RuntimeError("AI agent refuses to modify main")

    report = diagnostics.run()
    root = github.list_files("")
    paths = [x.get("path") for x in root if isinstance(x, dict) and x.get("path")]

    plan = _json(agent._call_ai(
        "Return ONLY JSON with keys summary, files, steps. Choose existing source files needed for this request. Max 8. Never choose secrets, .env, credentials, deployment keys, or main.",
        json.dumps({"request": request, "diagnostics": report, "repository_tree": paths}, indent=2),
    ))
    files = plan.get("files")
    if not isinstance(files, list) or not files or len(files) > 8 or not all(_safe(p) and p in paths for p in files):
        raise RuntimeError("Unsafe AI file plan")

    sources = {p: github.read_file(p) for p in files}
    source_payload = {p: {"sha": d["sha"], "content": d["content"]} for p, d in sources.items()}
    allowed_paths = list(sources.keys())
    patch = _json(agent._call_ai(
        "Return ONLY JSON with keys summary and changes. "
        "IMPORTANT: changes may be an empty list when no safe change is needed. "
        "Every change must be an object with path, complete content, and reason. "
        "The path MUST be exactly one of ALLOWED_PATHS. Never invent or rename paths. "
        "If no safe change is needed, return changes as []. Preserve unrelated behavior. "
        "Never modify secrets or credentials.",
        json.dumps({
            "request": request,
            "plan": plan,
            "ALLOWED_PATHS": allowed_paths,
            "SOURCE_FILES": source_payload,
        }, indent=2),
    ))
    changes = patch.get("changes")
    if not isinstance(changes, list) or len(changes) > 8:
        raise RuntimeError("Invalid AI change set")

    invalid = []
    for c in changes:
        if not isinstance(c, dict):
            invalid.append("change is not an object")
            continue
        path = c.get("path")
        if not _safe(path) or path not in sources or not isinstance(c.get("content"), str):
            invalid.append(f"invalid change path/content: {path!r}")
            continue
        if path.lower().endswith(".py"):
            try:
                compile(c["content"], path, "exec")
            except SyntaxError as exc:
                invalid.append(f"invalid Python for {path}: {exc}")
    if invalid:
        patch = _json(agent._call_ai(
            "Return ONLY JSON with keys summary and changes. "
            "Repair the previous patch. changes MUST be a list of zero or more objects. "
            "Every path MUST exactly match one of ALLOWED_PATHS and content MUST be a complete file string. "
            "If you cannot make a safe valid change, return changes as [].",
            json.dumps({
                "request": request,
                "ALLOWED_PATHS": allowed_paths,
                "SOURCE_FILES": source_payload,
                "previous_patch": patch,
                "validation_errors": invalid,
            }, indent=2),
        ))
        changes = patch.get("changes")
        if not isinstance(changes, list) or len(changes) > 8:
            raise RuntimeError("Invalid AI change set")
        for c in changes:
            if not isinstance(c, dict) or not _safe(c.get("path")) or c["path"] not in sources or not isinstance(c.get("content"), str):
                raise RuntimeError("Unsafe AI change")
            if c["path"].lower().endswith(".py"):
                try:
                    compile(c["content"], c["path"], "exec")
                except SyntaxError as exc:
                    raise RuntimeError(f"AI generated invalid Python for {c['path']}: {exc}") from exc

    result = {"request": request, "plan": plan, "proposed_changes": [{"path": c["path"], "reason": c.get("reason", "")} for c in changes], "applied": False}
    if not auto_apply:
        return result
    if not changes:
        result["status"] = "no_change_needed"
        return result

    commits = []
    for c in changes:
        current = github.read_file(c["path"])
        commits.append(github.update_file(c["path"], c["content"], current["sha"], "AI agent: fix " + c["path"]))

    latest = commits[-1]["commit_sha"]
    deploy = render.trigger_deploy(latest)
    deploy_id = deploy.get("id") or (deploy.get("deploy") or {}).get("id")
    result.update({"applied": True, "commits": commits, "deploy": deploy})

    if deploy_id:
        last = deploy
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(5)
            last = render.get_deploy(deploy_id)
            status = str(last.get("status") or (last.get("deploy") or {}).get("status") or "").lower()
            if status in {"live", "succeeded", "success", "failed", "canceled", "cancelled"}:
                break
        result["deployment_verification"] = {"deploy_id": deploy_id, "status": last.get("status") or (last.get("deploy") or {}).get("status")}

    test_url = settings.AI_AGENT_TEST_URL or render.get_service_url()
    if test_url:
        try:
            r = requests.get(test_url.rstrip("/") + "/health", timeout=30)
            result["post_deploy_test"] = {"url": test_url.rstrip("/") + "/health", "status_code": r.status_code, "ok": r.ok, "response": r.text[:500]}
        except requests.RequestException as exc:
            result["post_deploy_test"] = {"ok": False, "error": str(exc)}
    else:
        result["post_deploy_test"] = {"ok": False, "skipped": True, "reason": "No AI-agent test URL available"}

    return result
