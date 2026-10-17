#!/usr/bin/env bash
# Run only after the maintainer approves these exact commands on the real repository.
set -euo pipefail

repo=albertor03/behave-hive

# All matrix instances are required checks. Keep these names aligned with ci.yml.
for branch in main develop; do
  gh api --method PUT "repos/$repo/branches/$branch/protection" --input - <<'JSON'
{
  "required_status_checks":{"strict":true,"contexts":[
    "unit (ubuntu-latest, 3.11)", "unit (ubuntu-latest, 3.12)",
    "unit (ubuntu-latest, 3.13)", "unit (ubuntu-latest, 3.14)",
    "unit (macos-latest, 3.11)", "unit (macos-latest, 3.12)",
    "unit (macos-latest, 3.13)", "unit (macos-latest, 3.14)",
    "e2e", "packaging", "quality", "coverage", "actionlint"
  ]},
  "enforce_admins":true,
  "required_pull_request_reviews":{"required_approving_review_count":0,"dismiss_stale_reviews":true},
  "restrictions":null,
  "allow_force_pushes":false,
  "allow_deletions":false
}
JSON
done

reviewer=$(gh api users/albertor03 --jq .id)
gh api --method PUT "repos/$repo/environments/pypi" --input - <<JSON
{
  "reviewers":[{"type":"User","id":$reviewer}],
  "prevent_self_review":false,
  "can_admins_bypass":false,
  "deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}
}
JSON
gh api --method POST "repos/$repo/environments/pypi/deployment-branch-policies" -f name='v*' -f type=tag
