"""Run Alembic migrations programmatically at startup (SPEC §2, review B6)."""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
# First revision: the Phase 0 `jobs` table. DBs created by Phase 0's `create_all`
# have this schema but no `alembic_version` table.
BASELINE_REVISION = "d6be9ef0179f"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # Do not let env.py's fileConfig() replace the app's logging setup.
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_to_head(db_url: str) -> None:
    """Bring the database to the latest schema. Raises on failure (never run on a stale schema)."""
    cfg = _alembic_config(db_url)

    eng = create_engine(db_url)
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()

    if "jobs" in tables and "alembic_version" not in tables:
        logger.warning(
            "Database was created without Alembic (Phase 0 create_all); stamping baseline %s",
            BASELINE_REVISION,
        )
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")
