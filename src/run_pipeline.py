from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

from src.config import ROOT, db_path, league, relegation_spots, season
from src.ingest import ingest
from src.logging_config import configure_logging
from src.simulate import simulate

LOG = logging.getLogger("pipeline")


def run() -> None:
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path())
    vars_arg = json.dumps({"relegation_spots": relegation_spots()})
    dbt = [sys.executable, "-m", "dbt.cli.main"]
    base = dbt + ["run", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt"), "--vars", vars_arg]
    LOG.info("Starting pipeline season=%s league=%s", season(), league())
    ingest()
    subprocess.run(base + ["--select", "+mart_current_standings", "+int_remaining_fixtures"], cwd=ROOT, env=env, check=True)
    simulate()
    subprocess.run(base, cwd=ROOT, env=env, check=True)
    subprocess.run(dbt + ["test", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt"), "--vars", vars_arg], cwd=ROOT, env=env, check=True)
    LOG.info("Pipeline completed successfully")


if __name__ == "__main__":
    configure_logging()
    run()
