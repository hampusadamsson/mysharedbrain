-- 0005_audit_indexes: indexes matched to the queries the app actually issues.
--
-- Chosen from EXPLAIN QUERY PLAN output rather than guessed.
--
-- The measurable one is the whole-log counter summary that Activity renders
-- (kind + COUNT/MIN/MAX(ts)): on 200k audit rows it went 44ms -> 16ms, because
-- (kind, ts) answers it from the index alone instead of reading every row.
--
-- The other one is a plan guarantee that matters as the log grows and on skewed
-- data: with `idx_audit_note_kind` the file log filtered by kind — and its count
-- — is a single seek on both columns, the per-file counter summary no longer
-- needs a TEMP B-TREE for GROUP BY, and the count is answered by the index alone.
-- Without it SQLite may pick `idx_audit_kind` and filter `note_id` row by row,
-- which it does on a database that has never been ANALYZEd.
--
-- `idx_audit_note(note_id, id DESC)` stays: it is what makes an unfiltered file
-- log ordered and LIMIT-friendly, which the composite below cannot do (kind
-- sits before id in it).
--
-- Deliberately NOT added: (status, seq) on capture_entries. The existing
-- `idx_capture_status(status)` already returns status-filtered rows in seq order,
-- because SQLite appends the rowid to a non-unique index — a composite would be
-- redundant write cost for no plan change.

CREATE INDEX IF NOT EXISTS idx_audit_note_kind ON audit_log(note_id, kind, id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_kind_ts ON audit_log(kind, ts);
