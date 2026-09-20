import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .agent import agent
from .config import settings


logger = logging.getLogger("ai_backend_doctor")

router = APIRouter(prefix="/ai", tags=["AI Backend Doctor"])


class DiagnoseRequest(BaseModel):
    message: str = Field(default="Check my backend", min_length=1, max_length=2000)


def verify_ai_access(x_ai_admin_key: str | None):
    if not settings.AI_ADMIN_KEY:
        raise HTTPException(status_code=503, detail="AI admin key is not configured")
    if not x_ai_admin_key:
        raise HTTPException(status_code=401, detail="AI admin key required")
    if not secrets.compare_digest(x_ai_admin_key, settings.AI_ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid AI admin key")


@router.get("/health")
async def ai_health(x_ai_admin_key: str | None = Header(default=None)):
    verify_ai_access(x_ai_admin_key)
    return {"status": "ok", "service": "AI Backend Doctor"}


@router.post("/diagnose")
def ai_diagnose(
    payload: DiagnoseRequest,
    x_ai_admin_key: str | None = Header(default=None),
):
    verify_ai_access(x_ai_admin_key)
    try:
        return {"success": True, "result": agent.diagnose(payload.message)}
    except TimeoutError as exc:
        logger.warning("AI diagnosis timeout: %s", exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("AI diagnosis failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="AI diagnosis failed") from exc


@router.get("/inspect")
def ai_inspect(
    path: str,
    x_ai_admin_key: str | None = Header(default=None),
):
    verify_ai_access(x_ai_admin_key)

    if not path or path.startswith("/") or ".." in path.split("/"):
        raise HTTPException(
            status_code=400,
            detail="Use a repository-relative file path",
        )

    try:
        return {"success": True, "result": agent.inspect_file(path)}
    except TimeoutError as exc:
        logger.warning("File inspection timeout for path=%s", path)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "File inspection failed for path=%s: %s",
            path,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="File inspection failed") from exc
