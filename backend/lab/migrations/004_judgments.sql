CREATE TABLE judgments (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
    report TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, request_id)
);
CREATE TABLE judgment_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judgment_id TEXT NOT NULL REFERENCES judgments(id),
    revision INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(judgment_id, revision),
    UNIQUE(judgment_id, request_id)
);
PRAGMA user_version = 4;

