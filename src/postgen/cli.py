"""Entry point: `postgen` / `python -m postgen` starts the web UI. Everything else is in-app."""

from __future__ import annotations

import argparse
import logging

from postgen.config import get_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="postgen", description="LinkedIn post generator: serve the single-user web UI."
    )
    parser.add_argument("--host", help="bind address (default: POSTGEN_HOST)")
    parser.add_argument("--port", type=int, help="port (default: POSTGEN_PORT)")
    parser.add_argument("--reload", action="store_true", help="auto-reload (development only)")
    args = parser.parse_args(argv)

    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    uvicorn.run(
        "postgen.web.app:create_app",
        factory=True,
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
