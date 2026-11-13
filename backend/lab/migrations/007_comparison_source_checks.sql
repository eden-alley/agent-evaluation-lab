CREATE TABLE comparison_source_checks (
    comparison_id TEXT PRIMARY KEY REFERENCES comparisons(id),
    source_state TEXT NOT NULL CHECK (source_state IN ('unchanged', 'changed')),
    checked_at TEXT NOT NULL
);
PRAGMA user_version = 7;
