# Project status

Last reconciled: **2026-10-18**. This is the current checkout's implementation
and delivery snapshot. Earlier baseline numbers in local planning documents
remain historical measurements, not the current result.

The maintainer requested a documentation/Trello update and to leave unfinished
work pending. Implementation is paused. The tracking board is
[Personal projects](https://trello.com/b/Rb7Adhoj/personal-projects), with
[the consolidated backlog](https://trello.com/c/guKb4nCT).

## Verified local state

| Check | Latest verified result |
| --- | --- |
| Entire test suite | **691 passed** (664 unit + 27 e2e/packaging) |
| Unit tests | 664 passed |
| E2E and packaging tests | 27 passed (21 e2e, 6 packaging with clean pip/uv installs) |
| Library statements | **1660 / 1660 covered; 0 missing** |
| Library branches | **490 / 490 covered; 0 missing** |
| Coverage exclusions | 0 excluded lines; all 20 library Python files included |
| Quality | Ruff, source pylint duplication and pip-audit pass |
| Workflow validation | actionlint 1.7.12 and local workflow contract tests pass |
| Runtime | Python 3.14.7 on macOS; uv 0.13.1 in the project venv |

Coverage includes subprocesses and gates the entire library at exact 100%.
Statements and branches are separate metrics. Remote Linux/macOS/Python matrix
runs have not been observed; configured CI is not remote execution evidence.

Complexity: after HU-10 no function exceeds 10 and `pyproject.toml` has no `C901`
exception (details in the change's `baseline.md`, "After HU-10").

Reproduce the full suite with `.venv/bin` on PATH:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest -q
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest -m "not e2e and not packaging" --cov --cov-report=term-missing --cov-report=json:coverage.json
```

The sibling `behave-csv-demo` uses an editable installation. Its passing
sequential/parallel selections each return 0 with three passed scenarios and
identical IDs. The mixed run intentionally returns 1 with three passed and one
failed scenario. Cucumber schema, PNG evidence, configured HTML title/path and
Allure result counts are verified. The latest 16 generated report JSON/HTML
files contain neither the home prefix nor expanded run paths. HTML controls and
the decoded screenshot work with CSP active and no browser console errors.

## Delivery state

| Work | Current state | Remaining work |
| --- | --- | --- |
| HU-1: CSV Examples | Implemented and integrated | None in this story |
| HU-2: configuration | Implemented and integrated | HTML additions are tracked by HU-15 |
| HU-3: discovery, batching and execution | Both parts implemented and integrated | Later hardening changes belong to HU-9 |
| HU-4: reports | Implemented and integrated | Additional diagnostics belong to HU-11 |
| HU-5: pip/uv packaging | Implemented, integrated and verified | uv is available; no installation blocker |
| HU-6: example and usage docs | Implemented and integrated | Later docs track implemented extensions |
| HU-7: original Allure paths and HTML v2 | Implemented and integrated | Error privacy is implemented in HU-9; diagnostics remain HU-11 |
| HU-8: quality gates | Integrated into develop | Exact-100 strengthening is implemented in HU-16 |
| HU-9: privacy/security | Integrated into develop (`e8ac043`), reviews done | None in this story |
| HU-10: refactor | Integrated into develop (`a7a9e82`) | None in this story |
| HU-11: diagnostics | 10/10 tasks done on `feature/us-11-report-v3`, uncommitted | Authorized commit and integration |
| HU-12: hardened CI | Implemented and integrated into develop | Real CI, second-run cache and failing-run artifact evidence |
| HU-13: repository scanning | Implemented and integrated into develop | Real CodeQL/dependency-review execution |
| HU-14: release pipeline/settings script | Implemented and integrated into develop | Approved remote setup, publisher, rehearsal and release |
| HU-15: HTML name/path | Integrated into develop with HU-9 (`63d4c4c`) | Archive follow-up |
| HU-16: exact library coverage | Integrated into develop with HU-9 (`63d4c4c`) | Archive follow-up |

`develop` points to `a7a9e82` (HU-9, HU-10, HU-15 and HU-16 merged). The active branch
`feature/us-11-report-v3` holds the uncommitted HU-11 work. `main` still points to the
initial `fcb852b` commit. No Git remote is configured (`origin/HEAD` is only a local ref
used by `/security-review`), and no GitHub/PyPI publication or remote settings
application has been performed.

Already integrated merges: HU-8 `1c778a4`, HU-12 `3f78906`, HU-13 `662932f`,
HU-14 `69c85fd`. New commits/merges, pushes, tags, external settings and publication
remain subject to explicit maintainer instructions.

## OpenSpec tracking

OpenSpec planning is local and git-ignored. Implementation progress is distinct
from complete planning artifacts and from release/integration completion.

| Change | Checked tasks | Pending |
| --- | ---: | --- |
| `add-behave-hive-mvp` | **64/66** | 10.3 real CI and 10.5 approved repository publication |
| `harden-and-polish-behave-hive` | **47/48** | Trello closure (6.3) and integration of HU-11 |
| `add-github-actions-pipeline` | **18/24** | Settings/publisher, Trello/integration closure and real CI/release runs |
| `configure-html-report-name` | **6/6** | Review/integration/archive follow-up |
| `reach-full-library-coverage` | **16/16** | Review/integration/archive follow-up |

MVP 7.2 and 9.1 were reconciled with the verified uv installation and the full
624-test run with the maintainer's confirmation on 2026-10-18. They are no longer
pending. No change has been archived.

## Pending backlog

- [x] **HU-9 review:** done on 2026-10-18; see `baseline.md` "Security review".
  Findings 9 and 10 are deferred to HU-10.
- [x] **HU-10:** done on `feature/us-10-refactor`, `/simplify` included; see
  `baseline.md` "After HU-10".
- [x] **HU-11:** done on `feature/us-11-report-v3` (Allure attachments, environment
  metadata, run context, failures-first, outline groups and URL filters); uncommitted.
- [ ] **Integration:** commit and merge HU-11 into `develop` when requested.
- [ ] **GitHub:** approved public repository/remote creation and push; real CI
  matrix, second-run cache, forced-failure artifact and security-scan verification.
- [ ] **Repository/PyPI setup:** approved branch/environment settings and trusted
  publisher registration. The settings script is prepared, not applied.
- [ ] **Release:** select/approve the version, date the changelog, integrate to
  main, authorize the tag, pass the real dry run, then explicitly approve publish.
- [ ] **Closure:** finish the remaining OpenSpec/Trello tasks and archive in
  dependency order, with MVP before the dependent hardening closure.

Pending cards are parked in Trello **To Do**. Locally implemented checkitems
remain checked even when review, integration or remote verification keeps the
card pending; integrated stories with no remaining story work are in **Done**.
The reconciled project inventory has **19 cards: 9 Done, 10 To Do and none In
progress**. Cards for unrelated projects on the same board are outside this inventory.

## Evidence locations

- `coverage.json`, `coverage.xml`, `.coverage`: ignored canonical library coverage.
- `openspec/changes/harden-and-polish-behave-hive/security-verification.md` and
  `security-unit-coverage.txt`: latest hardening verification and pending review.
- `openspec/changes/reach-full-library-coverage/verification.md`: historical HU-16
  closure at 1422 statements/450 branches, before HU-9 added measured code.
- `openspec/changes/configure-html-report-name/verification.md`: HU-15 fallback
  and configured name/path checks.
- `openspec/changes/add-github-actions-pipeline/implementation.md`: local pipeline
  implementation and external checks still pending.
- `../behave-csv-demo/reports/validation-security/`: current real-demo report
  evidence; older validation directories are retained as historical snapshots.
