CREATE TABLE comparisons (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(project_id, request_id)
);
CREATE TABLE comparison_case_reports (
 id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL REFERENCES comparisons(id),
 case_id TEXT NOT NULL, revision INTEGER NOT NULL,
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 content TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(comparison_id, request_id), UNIQUE(comparison_id, case_id, revision)
);
CREATE TABLE comparison_reports (
 id TEXT PRIMARY KEY, comparison_id TEXT NOT NULL REFERENCES comparisons(id),
 request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 content TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(comparison_id, request_id)
);
PRAGMA user_version = 6;
