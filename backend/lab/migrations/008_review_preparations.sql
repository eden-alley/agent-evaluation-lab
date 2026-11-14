CREATE TABLE review_preparations (
    id TEXT PRIMARY KEY,
    comparison_id TEXT NOT NULL REFERENCES comparisons(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
PRAGMA user_version = 8;
