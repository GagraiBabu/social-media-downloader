from .github_tools import github
from .render_tools import render
from .api_tester import api_tester


class Diagnostics:
    def run(self, deep=False):
        report = {
            "repository": None,
            "render_service": None,
            "deployments": None,
            "backend_health": None,
            "api_tests": {},
            "deep": bool(deep),
            "errors": [],
        }

        try:
            repo = github.get_repository()
            report["repository"] = {
                "name": repo.get("full_name"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch"),
                "url": repo.get("html_url"),
            }
        except Exception as exc:
            report["errors"].append({"source": "github", "error": str(exc)})

        try:
            service = render.get_service()
            report["render_service"] = {
                "name": service.get("name"),
                "type": service.get("type"),
                "status": service.get("status"),
                "suspended": service.get("suspended"),
            }
        except Exception as exc:
            report["errors"].append({"source": "render", "error": str(exc)})

        try:
            deployments = render.get_deploys()
            items = deployments.get("items", []) if isinstance(deployments, dict) else deployments
            report["deployments"] = [
                {
                    "id": item.get("deploy", {}).get("id") if isinstance(item.get("deploy"), dict) else item.get("id"),
                    "status": item.get("deploy", {}).get("status") if isinstance(item.get("deploy"), dict) else item.get("status"),
                    "created_at": item.get("deploy", {}).get("createdAt") if isinstance(item.get("deploy"), dict) else item.get("createdAt"),
                    "commit": self._extract_commit(item),
                }
                for item in items[:10]
            ]
        except Exception as exc:
            report["errors"].append({"source": "render_deployments", "error": str(exc)})

        try:
            report["backend_health"] = api_tester.health_check()
        except Exception as exc:
            report["errors"].append({"source": "backend", "error": str(exc)})

        if deep:
            try:
                report["api_tests"]["default_info"] = api_tester.info_test()
            except Exception as exc:
                report["errors"].append({"source": "api_info_test", "error": str(exc)})

            try:
                report["api_tests"]["default_download"] = api_tester.download_test()
            except Exception as exc:
                report["errors"].append({"source": "api_download_test", "error": str(exc)})

            try:
                report["api_tests"]["platforms"] = api_tester.platform_tests()
            except Exception as exc:
                report["errors"].append({"source": "api_platform_tests", "error": str(exc)})

        report["summary"] = self._build_summary(report)
        return report

    @staticmethod
    def _extract_commit(item):
        if not isinstance(item, dict):
            return None
        deploy = item.get("deploy") if isinstance(item.get("deploy"), dict) else item
        if not isinstance(deploy, dict):
            return None
        for key in ("commit", "commitId", "commit_id", "commitID"):
            value = deploy.get(key)
            if isinstance(value, dict):
                value = value.get("id") or value.get("sha")
            if isinstance(value, str) and value:
                return value
        return None

    def _build_summary(self, report):
        problems = []

        health = report.get("backend_health")
        if health and not health.get("ok"):
            problems.append("Backend health check failed")

        for name, test in report.get("api_tests", {}).items():
            if name == "platforms" and isinstance(test, dict):
                if test.get("skipped"):
                    problems.append(f"Platform tests skipped: {test.get('reason', 'not configured')}")
                for platform_name, reason in (test.get("failed") or {}).items():
                    problems.append(f"Platform {platform_name} test failed: {reason}")
                continue

            if isinstance(test, dict) and not test.get("ok") and not test.get("skipped"):
                reason = test.get("failure_reason") or test.get("error") or f"{name} test failed"
                problems.append(f"API {name} test failed: {reason}")
            if isinstance(test, dict) and test.get("skipped"):
                problems.append(f"API {name} test skipped: {test.get('reason', 'not configured')}")

        service = report.get("render_service")
        if service:
            raw_status = service.get("status")
            if isinstance(raw_status, str) and raw_status.strip():
                status = raw_status.lower()
                if status not in {"live", "running", "available"}:
                    problems.append(f"Render service status: {status}")

        for error in report.get("errors", []):
            problems.append(f"{error['source']}: {error['error']}")

        if not problems:
            return {"status": "healthy", "problems": []}
        return {"status": "needs_attention", "problems": problems}


diagnostics = Diagnostics()
