import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .autofix import run_autofix


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ai-agent")
_lock = threading.Lock()
_jobs = {}


def create_job(request: str, auto_apply: bool = True):
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": time.time(),
            "request": request,
            "auto_apply": auto_apply,
        }
    _executor.submit(_run, job_id, request, auto_apply)
    return get_job(job_id)


def _run(job_id: str, request: str, auto_apply: bool):
    with _lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = time.time()
    try:
        result = run_autofix(request, auto_apply)
        with _lock:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["finished_at"] = time.time()
    except Exception as exc:
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["finished_at"] = time.time()


def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return dict(job)
