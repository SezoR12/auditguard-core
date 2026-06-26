from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.certification import router as certification_router
from app.api.tasks import router as tasks_router
from app.api.owner import router as owner_router
from app.api.owner_dashboard import router as owner_dashboard_router
from app.api.ledger import router as ledger_router
from app.api.notifications import router as notifications_router
from app.api.manager import router as manager_router
from app.api.exports import router as exports_router
from app.api.templates import router as templates_router
from app.api.admin import router as admin_router
from app.api.deps import require_role
from app.config import settings
from app.models import User

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup checks. Refuses to start in production on a BYPASSRLS role;
    otherwise records whether RLS is enforced so /health can surface it."""
    from app.database import assert_rls_enforceable

    app.state.rls_enforced = await assert_rls_enforceable()
    yield


app = FastAPI(title="AuditCore API", version="0.1.0", lifespan=lifespan)

# True if the DB connection enforces RLS, False if it bypasses (only reachable
# in non-production / ALLOW_RLS_BYPASS, since prod refuses to start). None until
# the lifespan startup check runs.
app.state.rls_enforced = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(certification_router)
app.include_router(tasks_router)
app.include_router(owner_router)
app.include_router(owner_dashboard_router)
app.include_router(ledger_router)
app.include_router(notifications_router)
app.include_router(manager_router)
app.include_router(exports_router)
app.include_router(templates_router)
app.include_router(admin_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    """Deep health check for external monitoring (DB + Redis connectivity)."""
    from datetime import datetime, timezone

    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.config import settings
    from app.database import engine

    checks: dict[str, str] = {}
    overall = "ok"

    # Database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    # RLS enforcement (set at startup). False => the DB role bypasses RLS, so
    # tenant isolation is inert — surface it as degraded for monitoring.
    rls_enforced = getattr(app.state, "rls_enforced", None)
    if rls_enforced is False:
        checks["rls"] = "bypassed"
        overall = "degraded"
    elif rls_enforced is True:
        checks["rls"] = "ok"
    else:
        checks["rls"] = "unknown"

    return {
        "status": overall,
        "checks": checks,
        "app": "AuditCore",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Example role-gated endpoints for Phase 1 acceptance tests
@app.get("/owner/dashboard")
async def owner_dashboard(user: User = Depends(require_role("owner"))) -> dict:
    return {"msg": f"مرحباً {user.full_name}", "scope": "owner"}


@app.get("/auditor/dashboard")
async def auditor_dashboard(user: User = Depends(require_role("auditor"))) -> dict:
    return {"msg": f"مرحباً {user.full_name}", "scope": "auditor"}


@app.get("/manager/dashboard")
async def manager_dashboard(user: User = Depends(require_role("manager"))) -> dict:
    return {"msg": f"مرحباً {user.full_name}", "scope": "manager"}


@app.get("/gm/dashboard")
async def gm_dashboard(user: User = Depends(require_role("gm"))) -> dict:
    return {"msg": f"مرحباً {user.full_name}", "scope": "gm"}
