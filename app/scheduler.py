import os
from urllib.parse import urlparse

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def _build_scheduler() -> AsyncIOScheduler:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        from apscheduler.jobstores.redis import RedisJobStore
        p = urlparse(redis_url)
        jobstore = RedisJobStore(
            host=p.hostname,
            port=p.port or 6379,
            password=p.password or None,
            db=int((p.path or "/0").lstrip("/") or 0),
            jobs_key="aegis:scheduler:jobs",
            run_times_key="aegis:scheduler:run_times",
        )
        return AsyncIOScheduler(
            timezone="Asia/Taipei",
            jobstores={"default": jobstore},
        )
    return AsyncIOScheduler(timezone="Asia/Taipei")


scheduler = _build_scheduler()
