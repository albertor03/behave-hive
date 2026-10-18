# Releasing

Publishing goes directly to **PyPI** through Trusted Publishing. A published
version and its filenames cannot be replaced, even after deletion.

## One-time setup (requires maintainer approval)

After creating the public repository and observing the first green CI run, review
the exact commands and JSON in [apply_settings.sh](../.github/scripts/apply_settings.sh).
With explicit maintainer approval, run `bash .github/scripts/apply_settings.sh`.
It requires all eight `unit (OS, Python)` matrix checks and `e2e`, `packaging`,
`quality`, `coverage`, `actionlint` on both `main` and `develop`, requires up-to-date
pull requests (zero approving code reviews for a solo maintainer), enforces these
rules for administrators and disallows force pushes and deletion.

The same script creates environment `pypi` with reviewer `albertor03`, manual
approval without administrator bypass, and deployment policy `v*` of type `tag`.
Self-review is permitted so the solo maintainer can approve their own release.
Review existing environment policies before reapplying; the script is intended
for initial setup and does not remove existing policies.

The maintainer must also register a pending trusted publisher in the PyPI web UI:

| Field | Value |
| --- | --- |
| PyPI project | `behave-hive` |
| GitHub owner | `albertor03` |
| Repository | `behave-hive` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

No PyPI API token or password is stored. Inspect settings after applying them:

```bash
gh api repos/albertor03/behave-hive/branches/main/protection
gh api repos/albertor03/behave-hive/branches/develop/protection
gh api repos/albertor03/behave-hive/environments/pypi
gh api repos/albertor03/behave-hive/environments/pypi/deployment-branch-policies
```

## Prepare and rehearse

1. Bump `project.version` in `pyproject.toml` on `develop` (and version assertions
   in the tests), and add `## [X.Y.Z] - YYYY-MM-DD` with notes to `CHANGELOG.md`.
2. Merge `develop` into `main` through a passing pull request.
3. Create the matching tag `vX.Y.Z` on that commit; accepted prereleases are
   `vX.Y.ZaN`, `vX.Y.ZbN` and `vX.Y.ZrcN`, matching the project version exactly.
4. With maintainer approval, push the tag and watch the Release workflow.
   Verification checks the tag format/version, its checked-out commit's
   reachability from `origin/main`, and a real date on the changelog section.
5. For the **first release**, leave the `pypi` deployment unapproved, cancel that
   initial run, and start the manual rehearsal below. The single release
   concurrency group must be free before the rehearsal can start.

In Actions, choose **Release -> Run workflow**, select the existing release **tag**
(not a branch), and keep `dry_run` checked. Equivalently:

```bash
gh workflow run release.yml --ref vX.Y.Z -f dry_run=true
gh run list --workflow release.yml
gh run view RUN_ID
```

The dry run verifies, builds the wheel and sdist once, checks metadata with
`twine check`, installs the wheel in clean environments with pip and uv, and
compares `behave-hive --version` to the tag. Download artifact `dist` to inspect
the exact files; `publish` and `github-release` must be skipped.

After a successful rehearsal, rerun the cancelled initial run (or manually run
the same tag with `dry_run=false`), watch all checks pass, and explicitly approve
the `pypi` deployment. The publish job alone gets OIDC permission. Only after
publication does GitHub Release receive write permission and attach the same
wheel/sdist and the version's changelog notes. Release runs never auto-cancel.

## Recovery

If verification, build or installation fails, nothing is published. Correct the
problem through `develop` and `main` and rehearse again. If publishing fails,
first inspect PyPI to determine whether any file was accepted. If **nothing** was
published, correct the configuration and rerun the failed job; a tag may only be
replaced with explicit maintainer approval before any files are published. If
any file was accepted, never try to replace that version: complete the release
record for those exact artifacts or prepare a new version. If only GitHub
Release failed, rerun that job with the original artifacts rather than rebuilding
or republishing. Do not use `skip-existing` to conceal a partial publication.
