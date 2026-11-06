CREATE TABLE IF NOT EXISTS dataset_collections (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, name)
);
CREATE TABLE IF NOT EXISTS dataset_drafts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    dataset_id TEXT NOT NULL REFERENCES dataset_collections(id),
    base_version_id TEXT,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    checks TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
    decision TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, request_id)
);
CREATE TABLE IF NOT EXISTS quality_reports (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES dataset_drafts(id),
    sequence INTEGER NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(draft_id, request_id),
    UNIQUE(draft_id, sequence)
);
CREATE TABLE IF NOT EXISTS dataset_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    dataset_id TEXT NOT NULL REFERENCES dataset_collections(id),
    draft_id TEXT NOT NULL UNIQUE REFERENCES dataset_drafts(id),
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(dataset_id, version)
);
CREATE TABLE IF NOT EXISTS external_tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client TEXT NOT NULL,
    tool TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_drafts_project ON dataset_drafts(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_quality_reports_draft ON quality_reports(draft_id, sequence);
PRAGMA user_version = 2;
