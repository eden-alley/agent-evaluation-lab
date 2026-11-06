CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('evaluation','business')),
    tags TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('builtin','user')),
    active_version_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    change_note TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','published')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(skill_id,version)
);
INSERT OR IGNORE INTO skills VALUES (
    'dataset-design', '评测集设计',
    '根据用户需求设计评测集；适用方法与内容待共同设计。',
    'evaluation', '["评测集","需求","用例设计"]', 'builtin', NULL,
    strftime('%Y-%m-%dT%H:%M:%fZ','now')
);
PRAGMA user_version = 3;
