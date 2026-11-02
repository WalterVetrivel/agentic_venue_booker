import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import FileResponse, HTMLResponse
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
    student_bookings,
    timetables,
    users,
    venues,
)
from app.config import get_settings
from app.services import documents as documents_svc


def create_app() -> FastAPI:
    mcp = mcp_server.make_session_manager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Load the search model in Ollama now rather than on the first search.
        threading.Thread(target=documents_svc.warm_up, daemon=True).start()
        async with mcp.run():
            yield

    app = FastAPI(title="Agentic Venue Booker", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.include_router(auth.router)
    app.include_router(venues.router)
    app.include_router(availability.router)
    app.include_router(users.router)
    app.include_router(timetables.router)
    app.include_router(bookings.router)
    app.include_router(student_bookings.router)
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

    _api_docs(app)

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


DOCS_ASSETS = Path(__file__).parent / "static" / "docs"


def _api_docs(app: FastAPI) -> None:
    """/docs and /redoc, with Swagger UI and ReDoc served locally so they work offline."""
    app.mount("/docs-assets", StaticFiles(directory=DOCS_ASSETS), name="docs-assets")
    title = app.title

    @app.get("/docs", include_in_schema=False)
    def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="/docs-assets/swagger-ui-bundle.js",
            swagger_css_url="/docs-assets/swagger-ui.css",
            swagger_favicon_url="/docs-assets/favicon-32x32.png",
            # No badge from validator.swagger.io: it needs the internet.
            swagger_ui_parameters={"validatorUrl": None},
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    def swagger_ui_redirect() -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()

    @app.get("/redoc", include_in_schema=False)
    def redoc() -> HTMLResponse:
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{title} - ReDoc",
            redoc_js_url="/docs-assets/redoc.standalone.js",
            redoc_favicon_url="/docs-assets/favicon-32x32.png",
            with_google_fonts=False,
        )


app = create_app()
