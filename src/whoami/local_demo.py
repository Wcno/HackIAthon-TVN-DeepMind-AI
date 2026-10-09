"""The real application hosted on a PC: verified q4 retrieval, durable SQLite, no billing setup."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from pathlib import Path

from whoami.backend.settings import Settings
from whoami.contracts import PROCESSED, OUTPUTS


def create_demo(settings: Settings, database: Path):
    from whoami.backend.app import create_app
    if settings.demo or settings.offline or not settings.gemini_api_key:
        raise ValueError("The complete online demo requires existing Gemini settings; no key is created or printed")
    configured = replace(settings, database=database, data_directory=PROCESSED, output_directory=OUTPUTS)
    app = create_app(configured)
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original_lifespan(app):
            index = app.state.assistant.index
            await asyncio.to_thread(index.search, "tránsitos diarios del Canal de Panamá", 5)
            if not index.mode.startswith("hybrid:"):
                raise RuntimeError(f"Demo refused degraded retrieval: {index.mode}")
            app.state.demo_readiness = {"ready": True, "retrieval": index.mode,
                                        "persistence": "local SQLite", "generation_daily_limit": configured.generation_daily_limit}
            print(json.dumps(app.state.demo_readiness), flush=True)
            yield

    app.router.lifespan_context = lifespan

    @app.get("/demo-readiness")
    def readiness():
        return app.state.demo_readiness

    return app


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", type=Path, required=True, help="persistent demo database; use an explicit separate path")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 inside a container behind a reverse proxy")
    parser.add_argument("--port", type=int, default=8765)


def main(args: argparse.Namespace) -> int:
    import uvicorn
    uvicorn.run(create_demo(Settings.from_environment(), args.database), host=args.host, port=args.port)
    return 0
