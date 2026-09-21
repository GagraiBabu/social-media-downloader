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


def _extract_deploy(item):
    if not isinstance(item, dict):
        return None
    deploy = item.get("deploy") if isinstance(item.get("deploy"), dict) else item
    if not isinstance(deploy, dict):
        return None
    commit = deploy.get("commit") or deploy.get("commitId") or deploy.get("commit_id")
    if isinstance(commit, dict):
        commit = commit.get("id") or commit.get("sha")
    return {
        "id": deploy.get("id"),
        "status": str(deploy.get("status") or "").lower(),
        "commit": commit,
    }


def _deploy_items(payload):
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
        if payload.get("id") or payload.get("status"):
            return [payload]
    return payload if isinstance(payload, list) else []


def _wait_for_deployment(commit_sha):
    """Wait for Render to serve the pushed commit, triggering it only if needed."""
    test_url = settings.AI_AGENT_TEST_URL or render.get_service_url()
    health_url = f"{test_url.rstrip('/')}/health" if test_url else None
    deadline = time.monotonic() + settings.AI_AGENT_DEPLOY_TIMEOUT_SECONDS
    last = None
    trigger_sent = False
    started = time.monotonic()

    while time.monotonic() < deadline:
        try:
            deploys = render.get_deploys()
            candidates = [_extract_deploy(item) for item in _deploy_items(deploys)]
            candidates = [x for x in candidates if x]
            matching = next((x for x in candidates if x.get("commit") == commit_sha), None)
            last = matching or (candidates[0] if candidates else None)

            if matching:
                status = matching.get("status", "")
                if status in {"live", "succeeded", "success", "deployed", "available"}:
                    return {"ok": True, "status": status, "deploy": matching, "health_url": health_url}
                if status in {"failed", "canceled", "cancelled", "deactivated"}:
                    return {"ok": False, "reason": f"Render deploy ended with status {status}", "deploy": matching, "health_url": health_url}

            if (
                settings.AI_AGENT_TRIGGER_DEPLOY
                and not trigger_sent
                and time.monotonic() - started >= 30
                and not matching
            ):
                try:
                    triggered = render.trigger_deploy(commit_sha)
                    trigger_sent = True
                    last = {"triggered": True, "response": triggered}
                except Exception as exc:
                    last = {"trigger_error": str(exc)}
                    trigger_sent = True

            if health_url and time.monotonic() - started >= 15:
                try:
                    health = requests.get(health_url, timeout=settings.AI_AGENT_HEALTH_TIMEOUT_SECONDS)
                    if health.ok and matching and matching.get("commit") == commit_sha:
                        return {"ok": True, "status": matching.get("status") or "healthy", "deploy": matching, "health_url": health_url}
                except requests.RequestException:
                    pass
        except Exception as exc:
            last = {"error": str(exc)}

        time.sleep(settings.AI_AGENT_DEPLOY_POLL_SECONDS)

    return {"ok": False, "reason": "Timed out waiting for Render deployment", "last": last, "health_url": health_url}


def _build_plan_and_patch(request, report, history):
    root = github.list_files("")
    paths = [x.get("path") for x in root if isinstance(x, dict) and x.get("path")]
    plan = _json(agent._call_ai(
        "Return ONLY JSON with keys summary, files, steps. Choose existing source files needed for the confirmed failure. Max 8. "
        "Never choose secrets, .env, credentials, deployment keys, or main. Do not change code merely for style. "
        "The goal is a concrete fix for a reproduced failure, not a speculative refactor.",
        json.dumps({"request": request, "diagnostics": report, "previous_attempts": history, "repository_tree": paths}, indent=2),
    ))
    files = plan.get("files")
    if not isinstance(files, list) or not files or len(files) > 8 or not all(_safe(p) and p in paths for p in files):
        raise RuntimeError("Unsafe AI file plan")

    sources = {p: github.read_file(p) for p in files}
    source_payload = {p: {"sha": d["sha"], "content": d["content"]} for p, d in sources.items()}
    allowed_paths = list(sources.keys())
    patch = _json(agent._call_ai(
        "Return ONLY JSON with keys summary and changes. Every change must be an object with path, complete content, and reason. "
        "The reason MUST cite a confirmed diagnostic finding or reproduced failure. "
        "The path MUST be exactly one of ALLOWED_PATHS. Never invent or rename paths. "
        "If no safe change is needed, return changes as []. Preserve unrelated behavior. Never modify secrets or credentials.",
        json.dumps({
            "request": request,
            "diagnostics": report,
            "previous_attempts": history,
            "plan": plan,
            "ALLOWED_PATHS": allowed_paths,
            "SOURCE_FILES": source_payload,
        }, indent=2),
    ))
    changes = patch.get("changes")
    if not isinstance(changes, list) or len(changes) > 8:
        raise RuntimeError("Invalid AI change set")
    invalid = _validate_changes(changes, sources)
    if invalid:
        patch = _json(agent._call_ai(
            "Return ONLY JSON with keys summary and changes. Repair the previous patch. changes must be a list of zero or more objects. "
            "Every non-empty change needs a non-empty reason tied to confirmed diagnostics. Paths must exactly match ALLOWED_PATHS. "
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
            raise RuntimeError("Invalid repaired AI change set")
        invalid = _validate_changes(changes, sources)
        if invalid:
            raise RuntimeError("Unsafe AI change: " + "; ".join(invalid[:3]))
    return plan, patch, changes


def _validate_changes(changes, sources):
    invalid = []
    for change in changes:
        if not isinstance(change, dict):
            invalid.append("change is not an object")
            continue
        path = change.get("path")
        if not _safe(path) or path not in sources or not isinstance(change.get("content"), str) or not isinstance(change.get("reason"), str) or not change.get("reason", "").strip():
            invalid.append(f"invalid path/content/reason: {path!r}")
            continue
        if path.lower().endswith(".py"):
            try:
                compile(change["content"], path, "exec")
            except SyntaxError as exc:
                invalid.append(f"invalid Python for {path}: {exc}")
    return invalid


def run_autofix(request, auto_apply=True, job_id=None):
    if settings.GITHUB_BRANCH == "main":
        raise RuntimeError("AI agent refuses to modify main")

    max_attempts = settings.AI_AGENT_MAX_REPAIR_ATTEMPTS
    deep = settings.AI_AGENT_DEEP_TESTS
    history = []
    report = diagnostics.run(deep=deep)

    if report.get("summary", {}).get("status") == "healthy":
        return {
            "request": request,
            "plan": {"summary": "Real backend diagnostics passed; no code change is justified.", "files": [], "steps": ["Run health check", "Run metadata test", "Run real download validation", "Leave ai-agent-dev unchanged"]},
            "proposed_changes": [],
            "applied": False,
            "status": "no_change_needed",
            "diagnostics": report,
            "attempts": [],
        }

    if not auto_apply:
        plan, patch, changes = _build_plan_and_patch(request, report, history)
        return {
            "request": request,
            "plan": plan,
            "proposed_changes": [{"path": c["path"], "reason": c.get("reason", "")} for c in changes],
            "applied": False,
            "status": "changes_proposed",
            "diagnostics": report,
        }

    result = {
        "request": request,
        "applied": False,
        "status": "failed",
        "attempts": [],
        "initial_diagnostics": report,
    }

    for attempt in range(1, max_attempts + 1):
        attempt_record = {"attempt": attempt, "diagnostics": report}
        plan, patch, changes = _build_plan_and_patch(request, report, history)
        attempt_record["plan"] = plan
        attempt_record["proposed_changes"] = [{"path": c["path"], "reason": c.get("reason", "")} for c in changes]

        if not changes:
            attempt_record["status"] = "no_safe_change"
            result["attempts"].append(attempt_record)
            result["status"] = "blocked_no_safe_change"
            break

        commit_marker = f" [AI-JOB:{job_id}]" if job_id else ""
        commit_message = f"AI agent: autonomous repair attempt {attempt}" + commit_marker
        commit = github.update_files_atomic(changes, commit_message)
        attempt_record["commit"] = commit
        result["applied"] = True

        deploy = _wait_for_deployment(commit["commit_sha"])
        attempt_record["deploy"] = deploy
        if deploy.get("ok"):
            verify = diagnostics.run(deep=True)
            attempt_record["verification"] = verify
            report = verify
            if verify.get("summary", {}).get("status") == "healthy":
                attempt_record["status"] = "verified_fixed"
                result["status"] = "completed_verified"
                result["final_diagnostics"] = verify
                result["attempts"].append(attempt_record)
                result["commits"] = [a.get("commit") for a in result["attempts"] if a.get("commit")]
                return result
            attempt_record["status"] = "verification_failed"
            history.append({"attempt": attempt, "commit": commit, "deploy": deploy, "verification": verify})
            report = verify
        else:
            attempt_record["status"] = "deploy_failed"
            history.append({"attempt": attempt, "commit": commit, "deploy": deploy})
            report = {"summary": {"status": "needs_attention", "problems": [deploy.get("reason", "Render deployment failed")]}, "deployment_failure": deploy}

        result["attempts"].append(attempt_record)

    result["final_diagnostics"] = report
    if result["status"] == "failed":
        result["status"] = "repair_attempts_exhausted"
    return result
