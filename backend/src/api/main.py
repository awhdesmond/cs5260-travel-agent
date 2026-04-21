import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env before LLM initialization
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.agents.supervisor.graph import SUPERVISOR_RECURSION_LIMIT, build_supervisor_graph
from src.agents.swarm.graph import SWARM_RECURSION_LIMIT, build_swarm_graph
from src.api.middleware.rate_limit import limiter
from src.api.routes.auth import router as auth_router
from src.api.routes.itineraries import router as itineraries_router
from src.api.routes.plan import router as plan_router
from src.api.routes.plan_edit import router as edit_router
from src.api.routes.plan_select import router as select_router
from src.api.routes.plan_stream import router as stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)

    try:
        app.state.supervisor_graph = build_supervisor_graph().compile()
        app.state.supervisor_recursion_limit = SUPERVISOR_RECURSION_LIMIT
    except Exception as e:
        logger.warning("Supervisor graph compilation failed: %s", e)
        app.state.supervisor_graph = None

    try:
        app.state.swarm_graph = build_swarm_graph().compile()
        app.state.swarm_recursion_limit = SWARM_RECURSION_LIMIT
    except Exception as e:
        logger.warning("Swarm graph compilation failed: %s", e)
        app.state.swarm_graph = None

    yield


app = FastAPI(
    title="CS5260 Travel Agent API",
    description="Travel planning API with Supervisor and Swarm orchestration modes",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# CORS registered after SlowAPI (middleware runs in reverse registration order)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://34.126.173.27"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.include_router(plan_router)
app.include_router(stream_router)
app.include_router(select_router)
app.include_router(edit_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(itineraries_router, prefix="/itineraries")


@app.get("/health")
async def health(request: Request):
    """Health check with per-graph readiness flags. Returns 503 if either graph failed."""
    supervisor_ready = getattr(request.app.state, "supervisor_graph", None) is not None
    swarm_ready = getattr(request.app.state, "swarm_graph", None) is not None
    is_degraded = not supervisor_ready or not swarm_ready
    content = {
        "status": "degraded" if is_degraded else "ok",
        "supervisor_ready": supervisor_ready,
        "swarm_ready": swarm_ready,
    }
    status_code = 503 if is_degraded else 200
    return JSONResponse(content=content, status_code=status_code)
