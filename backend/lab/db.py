"""SQLite connections and the initial schema."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > 7:
            raise RuntimeError("数据库版本高于当前应用，请使用对应版本的程序。")
        for target, filename in ((1, "001_initial.sql"), (2, "002_dataset_quality.sql"), (3, "003_skill_catalog.sql"), (4, "004_judgments.sql"), (5, "005_rechecking.sql"), (6, "006_comparisons.sql"), (7, "007_comparison_source_checks.sql")):
            if version < target:
                migration = Path(__file__).parent / "migrations" / filename
                conn.executescript("BEGIN IMMEDIATE;\n" + migration.read_text(encoding="utf-8-sig") + "\nCOMMIT;")


@contextmanager
def connect(path):
    conn = sqlite3.connect(path, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        with conn:
            yield conn
    finally:
        conn.close()
