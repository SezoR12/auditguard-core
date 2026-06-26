from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.certification import router as certification_router
from app.api.tasks import router as tasks_router
from app.api.owner import router as owner_router
from app.api.owner_dashboard import router as owner_dashboard_router
from app.api.ledger import router as ledger_router
from app.api.admin import router as admin_router
from app.api.deps import require_role
from app.config import settings
from app.models import User

app = FastAPI(title="AuditCore API", version="0.1.0")

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
app.include_router(admin_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


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
