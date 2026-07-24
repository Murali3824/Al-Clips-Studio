import json
import sys


def emit_progress(job_id: str, stage: str, status: str, percent: int, message: str) -> None:
    print(json.dumps({
        "type": "progress",
        "jobId": job_id,
        "stage": stage,
        "status": status,
        "percent": percent,
        "message": message,
    }))
    sys.stdout.flush()


def emit_error(job_id: str, stage: str, message: str) -> None:
    print(json.dumps({
        "type": "error",
        "jobId": job_id,
        "stage": stage,
        "message": message,
    }))
    sys.stdout.flush()
