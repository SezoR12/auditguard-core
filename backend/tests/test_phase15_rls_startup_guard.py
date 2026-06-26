import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Pure-logic suite: dummy env, no real DB needed (we patch the role probe).
os.environ.setdefault("SUPABASE_DB_HOST", "x")
os.environ.setdefault("SUPABASE_DB_USER", "x")
os.environ.setdefault("SUPABASE_DB_PASSWORD", "x")
os.environ.setdefault("SECRET_KEY", "s")
os.environ.setdefault("ENCRYPTION_MASTER_KEY", "k")
os.environ.setdefault("SUPABASE_URL", "https://t.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "s")

import asyncio
from app import database
from app.config import settings

P = []; F = []
def ck(n, c): (P if c else F).append(n); print(("PASS " if c else "FAIL ") + n)


async def run_case(*, bypass, environment, allow_bypass, probe_raises=False):
    """Drive assert_rls_enforceable with a patched role probe + settings."""
    orig_probe = database.connection_bypasses_rls
    orig_env = settings.ENVIRONMENT
    orig_allow = settings.ALLOW_RLS_BYPASS

    async def fake_probe():
        if probe_raises:
            raise RuntimeError("db down")
        return bypass

    database.connection_bypasses_rls = fake_probe
    settings.ENVIRONMENT = environment
    settings.ALLOW_RLS_BYPASS = allow_bypass
    try:
        try:
            result = await database.assert_rls_enforceable()
            return ("returned", result)
        except database.RLSBypassError:
            return ("raised", None)
    finally:
        database.connection_bypasses_rls = orig_probe
        settings.ENVIRONMENT = orig_env
        settings.ALLOW_RLS_BYPASS = orig_allow


async def main():
    # 1. Non-bypass role → enforceable (True), regardless of env.
    r = await run_case(bypass=False, environment="production", allow_bypass=False)
    ck("non-bypass role in prod → returns True", r == ("returned", True))

    # 2. Bypass role in PRODUCTION without escape hatch → refuse to start (raise).
    r = await run_case(bypass=True, environment="production", allow_bypass=False)
    ck("bypass role in prod → RLSBypassError raised", r == ("raised", None))

    # 3. Bypass role in production WITH escape hatch → start but flagged False.
    r = await run_case(bypass=True, environment="production", allow_bypass=True)
    ck("bypass role + ALLOW_RLS_BYPASS → returns False (degraded)", r == ("returned", False))

    # 4. Bypass role in development → start but flagged False (no raise).
    r = await run_case(bypass=True, environment="development", allow_bypass=False)
    ck("bypass role in dev → returns False (no raise)", r == ("returned", False))

    # 5. DB unreachable during probe → don't block startup (returns True).
    r = await run_case(bypass=True, environment="production", allow_bypass=False, probe_raises=True)
    ck("probe error → returns True (don't block on transient DB)", r == ("returned", True))

    # 6. Field defaults are safe: ALLOW_RLS_BYPASS=False, ENVIRONMENT=development.
    fields = type(settings).model_fields
    ck("ALLOW_RLS_BYPASS default is False", fields["ALLOW_RLS_BYPASS"].default is False)
    ck("ENVIRONMENT default is development", fields["ENVIRONMENT"].default == "development")

    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0


sys.exit(asyncio.run(main()))
