#!/usr/bin/env python3
"""Shellcheck every `run:` script in the workflows.

actionlint validates workflow structure and expressions, but its shellcheck
integration does not report the mistakes that actually bite: a script block
referencing a variable it never assigned (`set -u` then dies at runtime) passed
actionlint while failing in production. This extracts each script and hands it
to shellcheck directly.

GitHub expressions (`${{ … }}`) are not shell, so they are replaced with a
placeholder first; that keeps the parser on valid syntax while everything else
— unset variables, quoting, unused assignments — is still checked.

Usage: python3 .github/scripts/lint_workflow_shell.py
Exit code 1 when any script has findings.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

import yaml

WORKFLOWS = pathlib.Path(".github/workflows")

#: `${{ … }}` is not shell; a plain-word placeholder keeps it parseable.
EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.S)

#: Findings the placeholder itself provokes: comparisons look constant because
#: the substituted text is a literal.
IGNORED_CODES = ("SC2050", "SC2193")


def scripts(path: pathlib.Path) -> list[tuple[str, str]]:
    """(label, script) for every `run:` block in a workflow file."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found: list[tuple[str, str]] = []
    for job_name, job in (doc.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            script = step.get("run")
            if isinstance(script, str):
                label = step.get("name") or step.get("uses") or f"step {index}"
                found.append((f"{path.name} :: {job_name} :: {label}", script))
    return found


def main() -> int:
    checked = failed = 0
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for label, script in scripts(path):
            checked += 1
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
                fh.write(EXPRESSION.sub("github_expression", script))
                tmp = pathlib.Path(fh.name)
            try:
                proc = subprocess.run(
                    [
                        "shellcheck",
                        "-s",
                        "bash",
                        "-f",
                        "gcc",
                        "--exclude=" + ",".join(IGNORED_CODES),
                        str(tmp),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                tmp.unlink(missing_ok=True)
            if proc.returncode != 0:
                failed += 1
                print(f"::group::{label}")
                print(proc.stdout.replace(str(tmp), "script"))
                print("::endgroup::")
    print(f"{checked} run block(s) checked, {failed} with findings")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
