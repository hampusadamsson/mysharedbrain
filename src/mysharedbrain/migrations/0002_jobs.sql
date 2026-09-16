-- 0002_jobs: run history for scheduled librarian jobs.
-- Jobs themselves live in the config file (source of truth); this table only
-- records what happened, so the UI can show last run + next run.

CREATE TABLE job_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',  -- running | ok | error | skipped
    detail      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_job_runs_job ON job_runs(job_id, id DESC);
