CREATE TABLE checker_bindings (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(run_id, request_id)
);
CREATE TABLE check_runs (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
 binding_id TEXT NOT NULL REFERENCES checker_bindings(id),
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
 report TEXT, error TEXT, created_at TEXT NOT NULL,
 UNIQUE(run_id, request_id)
);
PRAGMA user_version = 5;
