"""Run independently: python -m coach.worker. No ephemeral BackgroundTasks."""
import logging
import time

from sqlalchemy import or_, select, update

from . import storage
from .analysis import GPXError, analyze
from .db import Run, initialize, session

log = logging.getLogger(__name__)


def process_one():
    stamp = time.time()
    with session() as db:
        query = select(Run).where(or_(Run.status == "queued", (Run.status == "processing") & (Run.lease_until < stamp)))
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        candidate = db.scalar(query.order_by(Run.created_at).limit(1))
        if candidate is None:
            return False
        if candidate.attempts >= 3:
            candidate.status = "failed"
            candidate.error = "처리 재시도 한도를 초과했습니다. 파일을 삭제하고 다시 업로드하세요."
            db.commit()
            return True
        lease = stamp + 120
        result = db.execute(update(Run).where(Run.id == candidate.id, Run.status == candidate.status,
                                              Run.attempts == candidate.attempts).values(
            status="processing", attempts=Run.attempts + 1, lease_until=lease))
        run_id, key, attempt = candidate.id, candidate.file_key, candidate.attempts
        db.commit()
        if not result.rowcount:
            return True
    try:
        analysis = analyze(storage.get(key))
        values = {"status": "completed", "analysis": analysis, "error": None, "lease_until": None}
    except GPXError as exc:
        values = {"status": "failed", "error": str(exc), "lease_until": None}
    except Exception:
        log.exception("Processing failure for run %s", run_id)
        values = {"status": "failed" if attempt >= 3 else "queued", "lease_until": None,
                  "error": "파일 저장소 읽기에 실패했습니다. 재시도 중입니다." if attempt < 3 else "파일 처리에 실패했습니다."}
    with session() as db:
        db.execute(update(Run).where(Run.id == run_id, Run.status == "processing", Run.lease_until == lease).values(**values))
        db.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    initialize()
    log.info("Running Coach worker ready")
    while True:
        if not process_one():
            time.sleep(1)


if __name__ == "__main__":
    main()
