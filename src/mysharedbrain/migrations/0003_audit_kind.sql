-- 0003_audit_kind: categorise audit entries so the UI can filter them.
--
-- `action` stays the precise verb ('read', 'patch', 'capture-applied', …);
-- `kind` is the coarse category a filter offers (read / find / write / delete /
-- move / capture / job). Backfilled for rows written before this column
-- existed, by the same rules as the app-side mapping.

ALTER TABLE audit_log ADD COLUMN kind TEXT NOT NULL DEFAULT 'other';

UPDATE audit_log SET kind = CASE
    WHEN action = 'read' THEN 'read'
    WHEN action = 'find' THEN 'find'
    WHEN action IN ('create', 'update', 'append', 'patch', 'frontmatter') THEN 'write'
    WHEN action IN ('delete', 'restore') THEN 'delete'
    WHEN action = 'move' THEN 'move'
    WHEN action LIKE 'capture-%' OR action = 'feedback' THEN 'capture'
    WHEN action LIKE 'job-%' THEN 'job'
    ELSE 'other'
END;

CREATE INDEX idx_audit_note ON audit_log(note_id, id DESC);
CREATE INDEX idx_audit_kind ON audit_log(kind, id DESC);
