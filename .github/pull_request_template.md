<!--
Thanks for contributing to AuditCore. Fill this in so reviewers and CI have
the context they need. See CONTRIBUTING.md for the full workflow.
-->

## Summary

<!-- What does this PR change, and why? -->

## Type of change

- [ ] `feat` — new functionality
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `ci` / `chore` — tooling / housekeeping
- [ ] `refactor` / `perf` / `test`

## How was this tested?

<!-- Be specific: which suites ran, against real Postgres/Redis or pure-logic? -->

- [ ] Backend: `cd backend && ./run_tests.sh` passes (all suites)
- [ ] Frontend: `npx tsc --noEmit` and `npm run build` pass
- [ ] Tested live against Postgres/Redis (not just written to spec)

## Migrations / schema

- [ ] No schema change
- [ ] Added Alembic migration (single linear head maintained)
- [ ] Added matching SQL mirror under `db/migrations/*.sql`

## Checklist

- [ ] No secrets committed; `.env` still gitignored, `.env.example` updated if needed
- [ ] Removed stray `__pycache__/` and any `package-lock.json`
- [ ] Both required CI checks expected to pass:
      `Backend tests (pure + DB integration)` and `Frontend build + type-check`
- [ ] RLS still enforced (DB tests run as non-superuser `appuser`)
