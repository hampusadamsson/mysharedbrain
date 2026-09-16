-- 0001_init: audit log + capture queue.
-- Applied once, in order, forward-only. Never edit this file after release —
-- add 0002_*.sql instead.

CREATE TABLE audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    note_id TEXT NOT NULL DEFAULT '',
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_audit_log_ts ON audit_log(ts);

CREATE TABLE capture_entries (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT NOT NULL UNIQUE,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    body        TEXT NOT NULL,
    note_id     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    reviewer    TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_capture_status ON capture_entries(status);
