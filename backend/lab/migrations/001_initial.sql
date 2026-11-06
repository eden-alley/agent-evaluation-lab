CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    description TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0), source_path TEXT NOT NULL,
    python_executable TEXT NOT NULL, entrypoint TEXT NOT NULL, config TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_check TEXT
);
PRAGMA user_version = 1;
