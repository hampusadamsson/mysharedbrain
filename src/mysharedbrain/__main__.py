"""MySharedBrain entrypoint: ``mysharedbrain`` serves the API+UI,
``mysharedbrain --mcp`` serves the MCP server over stdio.
"""

from __future__ import annotations

import sys


def main() -> None:
    if "--mcp" in sys.argv[1:]:
        from mysharedbrain.mcp import mcp

        mcp.run()
        return
    import uvicorn

    uvicorn.run("mysharedbrain.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
