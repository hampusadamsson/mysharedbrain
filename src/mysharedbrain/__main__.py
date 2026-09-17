"""MySharedBrain entrypoint: ``mysharedbrain`` serves the API+UI,
``mysharedbrain --mcp`` serves the MCP server over stdio.
"""

from __future__ import annotations

import sys

import uvicorn

from mysharedbrain.logging_setup import configure_logging
from mysharedbrain.mcp import mcp


def main() -> None:
    # Before anything else: without this the scheduler's INFO lines have no
    # handler and are silently dropped.
    configure_logging()

    if "--mcp" in sys.argv[1:]:
        mcp.run()
        return
    uvicorn.run("mysharedbrain.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
