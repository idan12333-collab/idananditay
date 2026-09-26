"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.instance import BUILD_ID, process_id
from app.core.logging import configure_logging, get_logger, log_event
from app.db.database import Database
from app.db.repository import Repository
from app.services.jobs import JobManager

WEB_DIR = Path(__file__).parent / "web" / "static"
logger = get_logger("main")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.initialize()
    repo = Repository(db)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_event(logger, "app started", version=__version__, build=BUILD_ID, pid=process_id(),
                  data_dir=str(settings.data_dir))
        yield
        app.state.jobs.shutdown()

    app = FastAPI(title="AI Photo Album", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo
    app.state.jobs = JobManager(settings, repo)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def cache_policy(request: Request, call_next):
        # Library/photo listings change with every scan; never let the browser reuse them.
        # The UI files (index.html, app.js) must be revalidated so an update is always picked up.
        response = await call_next(request)
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    return app
