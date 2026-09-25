"""MySharedBrain entrypoint: ``mysharedbrain`` serves the API+UI,
``mysharedbrain --mcp`` serves the MCP server over stdio.
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version

import uvicorn

from mysharedbrain.logging_setup import configure_logging
from mysharedbrain.mcp import mcp


def _version() -> str:
    try:
        return version("mysharedbrain")
    except PackageNotFoundError:
        return "0.0.0+local"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mysharedbrain",
        description="MySharedBrain — markdown vault API (+ built UI when present) "
        "or MCP server over stdio with --mcp.",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="serve the MCP server over stdio instead of the HTTP API",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="HTTP bind host (default: %(default)s)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="HTTP bind port (default: %(default)s)"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    return parser


def main(argv: list[str] | None = None) -> None:
    # Before anything else: without this the scheduler's INFO lines have no
    # handler and are silently dropped.
    configure_logging()

    raw = argv if argv is not None else sys.argv[1:]
    # Tolerate `uvx … mysharedbrain -- --help`: uvx forwards the `--` separator
    # verbatim and this CLI takes no positionals, so a bare `--` is never meaningful.
    args = build_parser().parse_args([a for a in raw if a != "--"])

    if args.mcp:
        mcp.run()
        return
    # Binds all interfaces on purpose: this runs in a container and is only
    # reachable through the cluster ingress.
    uvicorn.run(
        "mysharedbrain.app:app",
        host=args.host,  # nosec B104
        port=args.port,
    )


if __name__ == "__main__":
    main()
