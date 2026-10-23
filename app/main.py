import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.fpl.client import close_fpl_client
from app.routes.fixtures import router as fixtures_router
from app.routes.compare import router as compare_router
from app.routes.standings import router as standings_router
from app.services.storage import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to initialize and close database/HTTP clients."""
    await init_db()
    yield
    await close_db()
    await close_fpl_client()


app = FastAPI(title="Super League H2H", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register all modular route handlers (APIRouters)
app.include_router(fixtures_router)
app.include_router(compare_router)
app.include_router(standings_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
