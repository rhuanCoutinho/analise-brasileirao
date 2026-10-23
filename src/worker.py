import os

from redis import Redis
from rq import Queue, SimpleWorker


if __name__ == "__main__":
    connection = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    # SimpleWorker avoids os.fork, which is unavailable on Windows.
    SimpleWorker([Queue("updates", connection=connection)], connection=connection).work()
