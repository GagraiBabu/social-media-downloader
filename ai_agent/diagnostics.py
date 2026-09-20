from .github_tools import github
from .render_tools import render
from .api_tester import api_tester


class Diagnostics:
    def run(self):
        report = {
            "repository": None,
            "render_service": None,
            "deployments": None,
            "backend_health": None,
            "errors": [],
        }

        # GitHub repository
        try:
            repo = github.get_repository()

            report["repository"] = {
                "name": repo.get("full_name"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch"),
                "url": repo.get("html_url"),
            }
        except Exception as exc:
            report["errors"].append({
                "source": "github",
                "error": str(exc),
            })

        # Render service
        try:
            service = render.get_service()

            report["render_service"] = {
                "name": service.get("name"),
                "type": service.get("type"),
                "status": service.get("status"),
                "suspended": service.get("suspended"),
            }
        except Exception as exc:
            report["errors"].append({
                "source": "render",
                "error": str(exc),
            })

        # Recent Render deployments
        try:
            deployments = render.get_deploys()

            if isinstance(deployments, dict):
                items = deployments.get("items", [])
            else:
                items = deployments

            report["deployments"] = [
                {
                    "id": item.get("deploy", {}).get("id")
                    if isinstance(item.get("deploy"), dict)
                    else item.get("id"),
                    "status": item.get("deploy", {}).get("status")
                    if isinstance(item.get("deploy"), dict)
                    else item.get("status"),
                    "created_at": item.get("deploy", {}).get(
                        "createdAt"
                    )
                    if isinstance(item.get("deploy"), dict)
                    else item.get("createdAt"),
                }
                for item in items[:10]
            ]
        except Exception as exc:
            report["errors"].append({
                "source": "render_deployments",
                "error": str(exc),
            })

        # Backend health
        try:
            report["backend_health"] = api_tester.health_check()
        except Exception as exc:
            report["errors"].append({
                "source": "backend",
                "error": str(exc),
            })

        report["summary"] = self._build_summary(report)

        return report

    def _build_summary(self, report):
        problems = []

        health = report.get("backend_health")

        if health and not health.get("ok"):
            problems.append(
                "Backend health check failed"
            )

        service = report.get("render_service")

        if service:
            status = str(
                service.get("status", "")
            ).lower()

            if status and status not in {
                "live",
                "running",
                "available",
            }:
                problems.append(
                    f"Render service status: {status}"
                )

        for error in report.get("errors", []):
            problems.append(
                f"{error['source']}: {error['error']}"
            )

        if not problems:
            return {
                "status": "healthy",
                "problems": [],
            }

        return {
            "status": "needs_attention",
            "problems": problems,
        }


diagnostics = Diagnostics()
