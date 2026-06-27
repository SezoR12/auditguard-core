# Contributing to AuditCore

AuditCore (`auditguard-core`) uses a **pull-request workflow**. The `main` branch
is protected: direct pushes are discouraged (and flagged as a rule bypass), and
every change should land through a reviewed, CI-gated pull request.

## Branch protection on `main`

`main` requires the following before a merge:

- **Required status checks (strict / up-to-date with base):**
  - `Backend tests (pure + DB integration)`
  - `Frontend build + type-check`
- **Pull requests required** (no committing straight to `main`).
- **No force-pushes, no branch deletion.**
- `enforce_admins = false` — repository admins (and the Lovable integration) can
  still push directly when genuinely necessary, but this should be the exception.

See `scripts/setup_branch_protection.sh` to (re)apply these settings.

## Day-to-day workflow

1. **Sync `main`:**
   ```bash
   git checkout main
   git pull origin main
   ```
2. **Create a feature branch** using a descriptive prefix:
   - `feat/...` new functionality
   - `fix/...` bug fixes
   - `docs/...` documentation only
   - `ci/...` pipeline / tooling
   - `chore/...` housekeeping
   ```bash
   git checkout -b feat/sector-base-fields
   ```
3. **Make the change** and **test it for real** (see below).
4. **Commit** with a clear, scoped message (Conventional Commits style):
   ```bash
   git commit -m "feat(certify): capture sector base fields"
   ```
5. **Push the branch** and open a PR against `main`:
   ```bash
   git push -u origin feat/sector-base-fields
   ```
6. **Wait for CI** — both required checks must be green.
7. **Merge** once checks pass (squash or merge commit), then delete the branch.

## Running tests locally

The backend test suites are plain scripts (no pytest). DB-backed suites need
Postgres; notification/denylist suites need Redis. The full runner spins both up
and runs every suite:

```bash
cd backend
./run_tests.sh        # provisions test DB + non-superuser role, runs all suites
```

Each suite prints `=== N passed, M failed ===` and exits non-zero on any failure.

> **Important:** tests must connect as a **non-superuser** role (`appuser`).
> Supabase's `postgres` role has `BYPASSRLS=true`, so RLS (auditor
> zero-knowledge) only actually enforces under a non-superuser connection. The
> CI/test harness creates `appuser` with the right grants.

Frontend:

```bash
npm install --no-audit --no-fund
npx tsc --noEmit      # type-check
npm test              # Vitest + React Testing Library (jsdom)
npm run build         # production build
```

Frontend unit tests live next to the code as `*.test.tsx` and run under
**Vitest + React Testing Library** (config in `vitest.config.ts`, setup in
`src/test/setup.ts`). Route guards (`RequireRole`) and components with
non-trivial logic (`NotificationBell`, `ExportButtons`) and the `useAuth` hook
have coverage; pure presentational `ui/` primitives don't need tests. Use
`npm run test:watch` while developing and `npm run test:coverage` for a report.
The CI `Frontend build + type-check` job runs `npm test` before the build.

## Before you commit

- Remove stray `__pycache__/` directories and any `package-lock.json` (the
  project uses `bun.lock`; do not commit npm/yarn lockfiles).
- Never commit secrets. `.env` is gitignored — keep it that way. Use
  `.env.example` for documenting new variables.
- Keep the Alembic migration chain a **single linear head**
  (`001 → 002 → … → 007`). Add SQL mirrors under `db/migrations/*.sql` when the
  change must also be applied by `apply_rls.py` / `ci_setup_testdb.sh`.

## Dependency security scanning

Dependencies are watched two ways:

- **Dependabot** (`.github/dependabot.yml`) opens weekly update PRs for the
  frontend npm deps, the WhatsApp-bridge npm deps, the Python backend (`pip`),
  the Docker base images, and GitHub Actions. Review and merge these like any
  other PR (CI gates them).
- **CI `Dependency vulnerability scan` job** runs `pip-audit` (backend) and
  `npm audit --audit-level=high` (frontend + bridge) on every push/PR. It writes
  a findings summary to the job summary and uploads JSON/markdown reports as
  build artifacts (`dependency-scan-reports`, 14-day retention).

**Choice — the scan is currently NON-BLOCKING.** It is deliberately *not* one of
the required status checks, and its steps use `continue-on-error`, so a newly
disclosed transitive CVE cannot freeze all delivery. The signal still surfaces
(summary + artifacts + Dependabot PRs). To make it blocking once the backlog of
known findings is cleared: set the `continue-on-error` flags in the
`security-scan` job to `false` and add **Dependency vulnerability scan** to the
branch-protection required checks.

> There is a known backlog of high/critical findings in pinned backend deps
> (e.g. `python-jose`, `python-multipart`, `cryptography`) — these are tracked
> for remediation via Dependabot PRs and should be upgraded before flipping the
> scan to blocking.

## Commit message convention

```
<type>(<scope>): <short summary>

<optional body explaining what & why>
```

Types: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`, `perf`.
