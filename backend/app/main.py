from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from app import mcp_server
from app.api import (
    auth,
    availability,
    bookings,
    chat,
    documents,
    reports,
    settings,
    timetables,
    users,
    venues,
)
from app.config import get_settings


def create_app() -> FastAPI:
    mcp = mcp_server.make_session_manager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.run():
            yield

    app = FastAPI(title="Agentic Venue Booker", lifespan=lifespan)
    app.include_router(auth.router)
    app.include_router(venues.router)
    app.include_router(availability.router)
    app.include_router(users.router)
    app.include_router(timetables.router)
    app.include_router(bookings.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(settings.router)
    app.include_router(reports.router)

    # MCP clients connect to /mcp (or /mcp/); both reach the same handler.
    mcp_app = mcp_server.asgi_app(mcp)
    app.router.routes.append(Route("/mcp", mcp_app, methods=["GET", "POST", "DELETE"]))
    app.mount("/mcp", mcp_app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the built SvelteKit SPA (production). In development Vite serves it instead.
    build = get_settings().frontend_build_dir
    if build.is_dir():
        app.mount("/_app", StaticFiles(directory=build / "_app"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            file = (build / path).resolve()
            if path and file.is_file() and build.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(build / "index.html")

    return app


app = create_app()
