"""Logging setup: make the app's own logs actually visible.

Nothing configured logging, and Python's default only prints WARNING and above
through a last-resort handler — so the scheduler's INFO lines ("job started",
"next run at …") were being thrown away. This gives ``mysharedbrain.*`` a root
handler, without touching uvicorn's own loggers (it configures those itself, and
leaves the root logger alone).

Level comes from ``BRAIN_LOG_LEVEL`` (default INFO), so a container can turn it up
without a code change.
"""

from __future__ import annotations

import logging
import os

LOG_LEVEL_ENV = "BRAIN_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str | int | None = None) -> None:
    """Install a root handler for the app's loggers (safe to call twice).

    ``force=False`` on purpose: if the process already configured logging (a
    test runner, a supervisor), that decision wins.
    """
    resolved = (
        level if level is not None else os.environ.get(LOG_LEVEL_ENV, DEFAULT_LEVEL)
    )
    logging.basicConfig(level=resolved, format=FORMAT, force=False)
    # Our own logger at the level asked for, even when the root logger was
    # configured higher by whoever started us.
    logging.getLogger("mysharedbrain").setLevel(resolved)


__all__ = ["LOG_LEVEL_ENV", "configure_logging"]
