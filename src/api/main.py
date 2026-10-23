from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue

from src.config import db_path
from src.logging_config import configure_logging
from src.warehouse import connect

configure_logging()
LOG = logging.getLogger("api")
REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])


class UpdateResponse(BaseModel):
    job_id: str
    status: str = "queued"


def rows_as_dicts(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def query(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    try:
        conn = connect(read_only=True)
        try:
            return rows_as_dicts(conn.execute(sql, params))
        finally:
            conn.close()
    except Exception as exc:
        LOG.exception("Warehouse query failed")
        raise HTTPException(status_code=503, detail="Analytics warehouse is unavailable; run the pipeline first") from exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    LOG.info("API started", extra={"warehouse": str(db_path())})
    yield
    LOG.info("API stopped")


app = FastAPI(title="Relegation Analytics API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request, call_next):
    import time
    started = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        endpoint = getattr(request.scope.get("route"), "path", "unmatched")
        status = str(getattr(locals().get("response"), "status_code", 500))
        duration = time.perf_counter() - started
        REQUESTS.labels(request.method, endpoint, status).inc()
        LATENCY.labels(request.method, endpoint).observe(duration)
        LOG.info("HTTP request", extra={"method": request.method, "endpoint": endpoint,
                                        "status": int(status), "duration_seconds": round(duration, 6)})


@app.get("/healthz")
def health() -> dict:
    try:
        conn = connect(read_only=True)
        conn.execute("select 1").fetchone()
        conn.close()
        return {"status": "ok", "warehouse": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="warehouse unavailable") from exc


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/leagues/{league}/teams")
def teams(league: str, season: str = Query(..., pattern=r"^\d{4}$"),
          limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    league = league.upper()
    if not league.isalnum() or len(league) > 4:
        raise HTTPException(status_code=422, detail="Invalid league code")
    rows = query("""select season, league, team, position, played, wins, draws, losses,
                         goals_for, goals_against, goal_difference, points, league_size, relegation_spots
                  from mart_current_standings where season = ? and league = ?
                  order by position limit ? offset ?""", [season, league, limit, offset])
    return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}


@app.get("/api/v1/leagues/{league}/probabilities")
def probabilities(league: str, season: str = Query(..., pattern=r"^\d{4}$"),
                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    league = league.upper()
    if not league.isalnum() or len(league) > 4:
        raise HTTPException(status_code=422, detail="Invalid league code")
    rows = query("""with latest as (
                      select max(estimated_at) as estimated_at from mart_relegation_estimates
                      where season = ? and league = ?
                  )
                  select e.season, e.league, e.team, e.estimated_at, e.relegation_probability,
                         e.simulations, e.relegation_spots, e.position, e.points, e.played, e.goal_difference
                  from mart_relegation_estimates e join latest l using (estimated_at)
                  where e.season = ? and e.league = ?
                  order by e.relegation_probability desc, e.position limit ? offset ?""",
                 [season, league, season, league, limit, offset])
    return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}


@app.get("/api/v1/leagues/{league}/teams/{team}/history")
def estimate_history(league: str, team: str, season: str = Query(..., pattern=r"^\d{4}$"),
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    league = league.upper()
    if not league.isalnum() or len(league) > 4:
        raise HTTPException(status_code=422, detail="Invalid league code")
    rows = query("""select season, league, team, estimated_at, relegation_probability,
                         simulations, relegation_spots, random_seed
                  from mart_relegation_estimates where season = ? and league = ? and lower(team) = lower(?)
                  order by estimated_at desc limit ? offset ?""", [season, league, team, limit, offset])
    return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}


@app.get("/api/v1/leagues/{league}/historical-thresholds")
def historical_thresholds(league: str, limit: int = Query(10, ge=1, le=100),
                          offset: int = Query(0, ge=0)) -> dict:
    league = league.upper()
    if not league.isalnum() or len(league) > 4:
        raise HTTPException(status_code=422, detail="Invalid league code")
    rows = query("""select season, last_safe_team, last_safe_points,
                         last_relegated_team, last_relegated_points,
                         avg(last_safe_points) over () as five_season_avg_safe_points,
                         avg(last_relegated_points) over () as five_season_avg_relegated_points
                  from mart_historical_relegation_thresholds
                  where league = ? order by season limit ? offset ?""", [league, limit, offset])
    return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}


@app.get("/api/v1/leagues/{league}/historical-relegated-teams")
def historical_relegated_teams(league: str, limit: int = Query(100, ge=1, le=500),
                               offset: int = Query(0, ge=0)) -> dict:
    league = league.upper()
    if not league.isalnum() or len(league) > 4:
        raise HTTPException(status_code=422, detail="Invalid league code")
    rows = query("""select season, relegated_team, final_position, points
                  from mart_historical_relegated_teams where league = ?
                  order by season desc, final_position limit ? offset ?""", [league, limit, offset])
    return {"items": rows, "limit": limit, "offset": offset, "count": len(rows)}


@app.post("/api/v1/updates", response_model=UpdateResponse, status_code=202)
def enqueue_update() -> UpdateResponse:
    try:
        redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        redis.ping()
        queue = Queue("updates", connection=redis)
        job = queue.enqueue("src.queue_tasks.run_update", job_timeout=1800, result_ttl=86400)
        LOG.info("Pipeline update queued", extra={"job_id": job.id})
        return UpdateResponse(job_id=job.id)
    except Exception as exc:
        LOG.exception("Could not enqueue pipeline update")
        raise HTTPException(status_code=503, detail="Update queue unavailable") from exc
