"""Small polling worker for the transactional outbox. Delivery is simulated locally."""
import json, logging, os, time
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import SessionLocal, OutboxJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("opsflow.worker")
MAX_ATTEMPTS=int(os.getenv("OUTBOX_MAX_ATTEMPTS","5"))
POLL_SECONDS=float(os.getenv("OUTBOX_POLL_SECONDS","2"))

def process_one(db: Session) -> bool:
    job=db.scalar(select(OutboxJob).where(OutboxJob.status=="pending").order_by(OutboxJob.id).limit(1))
    if not job: return False
    # Single-process demo worker. In production use SELECT ... FOR UPDATE SKIP LOCKED.
    job.status="processing"; db.commit(); db.refresh(job)
    try:
        payload=json.loads(job.payload)
        # Replace this log with an idempotent notification handler when a real channel is chosen.
        log.info("Processed outbox event %s: %s",job.event_key,payload)
        job.status="processed"; job.attempts+=1; db.commit()
    except Exception:
        db.rollback()
        retry=db.get(OutboxJob,job.id)
        if retry:
            retry.attempts+=1
            retry.status="failed" if retry.attempts>=MAX_ATTEMPTS else "pending"
            db.commit()
            if retry.status=="pending": time.sleep(min(2 ** retry.attempts,30))
    return True

def main():
    log.info("OpsFlow outbox worker started; polling every %ss",POLL_SECONDS)
    while True:
        with SessionLocal() as db:
            did_work=process_one(db)
        if not did_work: time.sleep(POLL_SECONDS)
if __name__=="__main__": main()
