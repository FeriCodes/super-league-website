import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.fpl.client import close_fpl_client
from app.routes.home import router as home_router
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

# Initialize Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")


# Custom exception handler to render the errors.html template on HTTP exceptions
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "request": request,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
        status_code=exc.status_code,
    )


# Mount static files directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register all modular route handlers (APIRouters)
app.include_router(home_router)
app.include_router(fixtures_router)
app.include_router(compare_router)
app.include_router(standings_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
