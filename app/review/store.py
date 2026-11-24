import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT,
    owner TEXT NOT NULL DEFAULT '', owner_since TEXT
);
CREATE TABLE IF NOT EXISTS handovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, at TEXT NOT NULL
);"""

MIGRATIONS = (
    ("owner", "ALTER TABLE runs ADD COLUMN owner TEXT NOT NULL DEFAULT ''"),
    ("owner_since", "ALTER TABLE runs ADD COLUMN owner_since TEXT"),
)


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            for name, statement in MIGRATIONS:
                if name not in columns:
                    db.execute(statement)
            yield db

    def register(self, run_id, report, actor):
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO runs(id,report,created,owner,owner_since) VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (
                    run_id,
                    json.dumps(report, ensure_ascii=False),
                    report["manifest"]["created"],
                    actor,
                    report["manifest"]["created"],
                ),
            )
            if cursor.rowcount == 1:
                db.execute(
                    "INSERT INTO handovers(run_id,actor,action,at) VALUES (?,?,?,?)",
                    (run_id, actor, "CLAIM", report["manifest"]["created"]),
                )
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise DomainIssue("RUN_NOT_FOUND")
            result = dict(row)
            result["report"] = json.loads(result["report"])
            result["handovers"] = [
                dict(entry)
                for entry in db.execute(
                    "SELECT actor,action,at FROM handovers WHERE run_id=? ORDER BY id",
                    (run_id,),
                )
            ]
        return result

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,created,status,revision,note,owner,owner_since FROM runs ORDER BY created DESC,id LIMIT 50"
                )
            ]

    def revise(self, run_id, revision, status, note, actor, now):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=? AND owner=?",
                (status, note, now, run_id, revision, actor),
            )
            if cursor.rowcount != 1:
                row = db.execute(
                    "SELECT owner FROM runs WHERE id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise DomainIssue("RUN_NOT_FOUND")
                if row["owner"] != actor:
                    raise DomainIssue("OWNER_MISMATCH")
                raise DomainIssue("STALE_REVIEW")
        return self.load(run_id)

    def claim(self, run_id, actor, stamp, threshold):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET owner=?,owner_since=? WHERE id=? AND (owner='' OR owner_since<=?)",
                (actor, stamp, run_id, threshold),
            )
            if cursor.rowcount != 1:
                row = db.execute(
                    "SELECT owner FROM runs WHERE id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise DomainIssue("RUN_NOT_FOUND")
                raise DomainIssue("OWNER_ACTIVE")
            db.execute(
                "INSERT INTO handovers(run_id,actor,action,at) VALUES (?,?,?,?)",
                (run_id, actor, "TAKEOVER", stamp),
            )
        return self.load(run_id)

    def release(self, run_id, actor, stamp):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET owner='',owner_since=NULL WHERE id=? AND owner=?",
                (run_id, actor),
            )
            if cursor.rowcount != 1:
                row = db.execute(
                    "SELECT owner FROM runs WHERE id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise DomainIssue("RUN_NOT_FOUND")
                raise DomainIssue("OWNER_MISMATCH")
            db.execute(
                "INSERT INTO handovers(run_id,actor,action,at) VALUES (?,?,?,?)",
                (run_id, actor, "RELEASE", stamp),
            )
        return self.load(run_id)
