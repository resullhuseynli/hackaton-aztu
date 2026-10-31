import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def to_db_time(moment: datetime | None) -> str | None:
    return moment.strftime(TIME_FORMAT) if moment else None


def from_db_time(value: str | None) -> datetime | None:
    return datetime.strptime(value, TIME_FORMAT) if value else None


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # WAL lets the API read while the simulator writes.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    def recreate(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{self.path}{suffix}").unlink(missing_ok=True)
        self.init_schema()
