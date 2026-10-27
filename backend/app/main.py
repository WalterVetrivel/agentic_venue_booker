from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, availability, bookings, timetables, users, venues
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Agentic Venue Booker")
    app.include_router(auth.router)
    app.include_router(venues.router)
    app.include_router(availability.router)
    app.include_router(users.router)
    app.include_router(timetables.router)
    app.include_router(bookings.router)

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
