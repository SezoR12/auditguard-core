from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from typing import AsyncGenerator

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    # Supabase pooler in transaction mode requires statement_cache_size=0
    connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def connection_bypasses_rls() -> bool:
    """True if the role the app connects as can bypass Row-Level Security.

    Superusers and roles with rolbypassrls ignore every RLS policy, which would
    silently disable tenant isolation / auditor zero-knowledge. We check both.
    """
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT rolsuper OR rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).scalar_one_or_none()
    return bool(row)


class RLSBypassError(RuntimeError):
    """Raised at startup when a production app connects with a BYPASSRLS role."""


async def assert_rls_enforceable() -> bool:
    """Verify the DB connection actually enforces RLS.

    Returns True if RLS is enforceable. If the role bypasses RLS:
      - in production (ENVIRONMENT=production) without ALLOW_RLS_BYPASS → raise
        RLSBypassError (refuse to start);
      - otherwise → log CRITICAL and return False (caller may degrade /health).
    """
    import logging

    log = logging.getLogger("auditcore.security")
    try:
        bypass = await connection_bypasses_rls()
    except Exception as exc:  # noqa: BLE001 - DB unreachable at startup
        log.warning("Could not verify RLS enforcement (DB unreachable): %s", exc)
        return True  # don't block startup purely on a transient DB hiccup

    if not bypass:
        return True

    is_prod = settings.ENVIRONMENT.lower() == "production"
    msg = (
        "DB connection role can BYPASS Row-Level Security "
        "(superuser or rolbypassrls=true). Tenant isolation and auditor "
        "zero-knowledge are NOT enforced. Switch SUPABASE_DB_USER to a "
        "non-privileged role (see SECURITY.md → Provisioning the runtime DB role)."
    )
    if is_prod and not settings.ALLOW_RLS_BYPASS:
        log.critical(msg)
        raise RLSBypassError(msg)
    log.critical("%s (continuing: ENVIRONMENT=%s, ALLOW_RLS_BYPASS=%s)",
                 msg, settings.ENVIRONMENT, settings.ALLOW_RLS_BYPASS)
    return False


async def set_user_role(session: AsyncSession, role: str) -> None:
    """Set the RLS app.current_user_role for the current connection.

    Kept for back-compat (workers/tests that only need the role GUC). For
    request handling prefer set_user_context, which also populates the
    id/company/branch/auth GUCs the users + audit_tasks policies rely on.
    """
    await session.execute(text("SELECT set_config('app.current_user_role', :role, true)"),
                          {"role": role})


async def set_user_context(
    session: AsyncSession,
    *,
    role: str | None = None,
    user_id: str | None = None,
    company_id: str | None = None,
    branch_id: str | None = None,
    auth_user_id: str | None = None,
    auth_email: str | None = None,
) -> None:
    """Populate the per-connection RLS context GUCs.

    Any value left as None is written as '' (empty) so the typed SQL accessors
    (public.current_app_*()) resolve to NULL. Use auth_user_id/auth_email BEFORE
    the profile lookup so the self-read passes the public.users RLS policy.
    """
    await session.execute(
        text(
            "SELECT set_config('app.current_user_role',      :role,    true),"
            "       set_config('app.current_user_id',        :uid,     true),"
            "       set_config('app.current_company_id',      :cid,     true),"
            "       set_config('app.current_branch_id',       :bid,     true),"
            "       set_config('app.current_auth_user_id',    :auth,    true),"
            "       set_config('app.current_auth_email',      :email,   true)"
        ),
        {
            "role": role or "",
            "uid": user_id or "",
            "cid": company_id or "",
            "bid": branch_id or "",
            "auth": auth_user_id or "",
            "email": auth_email or "",
        },
    )
