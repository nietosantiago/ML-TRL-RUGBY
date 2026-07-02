"""
Migración: crea las tablas de análisis de video (video_analyses, match_events)
en una base ya existente. Idempotente (CREATE TABLE IF NOT EXISTS).

USO:
  python scripts/migrate_video_events.py
  DATABASE_URL=postgresql://... python scripts/migrate_video_events.py
"""

import os
import logging

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_video_events")

SQL = """
CREATE TABLE IF NOT EXISTS video_analyses (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    video_name      VARCHAR(255) NOT NULL,
    duration_seconds FLOAT,
    fps             FLOAT,
    pipeline_version VARCHAR(20),
    params          JSONB,
    analyzed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS match_events (
    id          SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    event_type  VARCHAR(20) NOT NULL,
    t_start     FLOAT NOT NULL,
    t_end       FLOAT,
    confidence  FLOAT,
    n_players   INTEGER,
    x_norm      FLOAT,
    y_norm      FLOAT,
    meta        JSONB,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_match_events_analysis
    ON match_events(analysis_id, event_type);
"""


def get_connection():
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "trl_db"),
        user=os.getenv("DB_USER", "trl_user"),
        password=os.getenv("DB_PASSWORD", "trl_password"),
    )


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()
        logger.info("Tablas video_analyses y match_events listas.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
