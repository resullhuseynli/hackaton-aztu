"""Smart Transit & Crowdsourcing Engine API.

Run: uvicorn app.main:app --reload   (from the backend folder, after `python -m app.seed`)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.business.errors import NotFoundError, ValidationError
from app.config import settings
from app.container import Container
from app.controller import live_controller, operator_controller, passenger_controller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container(settings)
    if not settings.db_path.exists() or not container.network_repo.line_ids_with_routes():
        raise RuntimeError("Database is empty. Run `python -m app.seed` in the backend folder first.")
    container.engine.start()
    app.state.container = container
    engine_task = asyncio.create_task(container.engine.run())
    yield
    engine_task.cancel()


app = FastAPI(
    title="Smart Transit & Crowdsourcing Engine",
    description="Bakı avtobus şəbəkəsi üçün real-vaxt mövqe, ETA, sıxlıq analitikası və operator xəbərdarlıqları.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NotFoundError)
def not_found(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
def invalid(_: Request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(passenger_controller.router)
app.include_router(operator_controller.router)
app.include_router(operator_controller.demo_router)
app.include_router(live_controller.router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}
