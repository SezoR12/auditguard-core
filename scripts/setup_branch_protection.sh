#!/usr/bin/env bash
#
# Apply branch protection to `main`: require both CI checks + PRs, block force
# pushes/deletions. Re-runnable.
#
# Usage:
#   GITHUB_TOKEN=ghp_xxx ./scripts/setup_branch_protection.sh [owner/repo]
#
# Requires a token with admin rights on the repo. The required status-check
# CONTEXTS must exactly match the CI job `name:` values in
# .github/workflows/ci.yml.
#
set -euo pipefail

REPO="${1:-SezoR12/auditguard-core}"
: "${GITHUB_TOKEN:?Set GITHUB_TOKEN (admin scope) in the environment}"

read -r -d '' BODY <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Backend tests (pure + DB integration)", "Frontend build + type-check"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0, "dismiss_stale_reviews": true },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

curl -fsS -X PUT \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO}/branches/main/protection" \
  -d "${BODY}" >/dev/null && echo "✓ branch protection applied to ${REPO}@main" \
  || { echo "✗ failed (need admin token; private repos need GitHub Pro)"; exit 1; }
