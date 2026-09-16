-- 0004_capture_question: open questions become their own kind, and entries the
-- system files on its own are marked automated.
--
-- Before this, the librarian filed an unanswered question as a 'request' with a
-- fixed body prefix. Those are reclassified, and flagged automated, so reviewers
-- can tell machine-filed work from a person's feedback.

ALTER TABLE capture_entries ADD COLUMN automated INTEGER NOT NULL DEFAULT 0;

UPDATE capture_entries
   SET kind = 'question', automated = 1
 WHERE kind = 'request'
   AND body LIKE 'Unanswered question:%';
