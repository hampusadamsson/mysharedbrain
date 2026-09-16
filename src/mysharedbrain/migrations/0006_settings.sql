-- 0006_settings: the settings themselves, kept in the vault database.
--
-- Settings used to live in a plain YAML file that the settings page rewrote.
-- They are state like everything else in `.brain/`, so they belong here: a row
-- survives the file being absent or mounted read-only, it cannot be half-written
-- by an editor, and it is backed up with the rest of the brain.
--
-- One row, enforced by the CHECK: the document is the whole config as JSON.
-- The YAML file stays as the starting point (a configmap on a fresh container)
-- and the environment still overrides both.

CREATE TABLE settings (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    document   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
