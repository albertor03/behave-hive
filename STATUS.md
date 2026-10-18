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
| Entire test suite | **624 passed** in one run |
| Unit tests | 607 passed |
| E2E tests | 12 passed |
| Packaging tests | 5 passed, including clean pip/uv installs |
| Library statements | **1494 / 1494 covered; 0 missing** |
| Library branches | **474 / 474 covered; 0 missing** |
| Coverage exclusions | 0 excluded lines; all 20 library Python files included |
| Quality | Ruff, source pylint duplication and pip-audit pass |
| Workflow validation | actionlint 1.7.12 and local workflow contract tests pass |
| Runtime | Python 3.14.7 on macOS; uv 0.13.1 in the project venv |

Coverage includes subprocesses and gates the entire library at exact 100%.
Statements and branches are separate metrics. Remote Linux/macOS/Python matrix
runs have not been observed; configured CI is not remote execution evidence.

An isolated complexity measurement still finds `_find_tables` 11,
`read_csv_rows` 11, `execute_batches` 14 and `_run_locked` 11 (limit 10).
Configured Ruff passes because the temporary module exceptions remain. HU-10
must close these current findings as well as its planned refactor; older counts
and the earlier `merge` finding must not be treated as the current inventory.

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
| HU-9: privacy/security | Tasks 3.1–3.8 implemented and locally verified | Required full-tree reviews, then authorized integration |
| HU-10: refactor | Not implemented | All nine tasks, including removing temporary complexity exceptions |
| HU-11: diagnostics | Not implemented | All ten tasks, including Allure attachments and environment metadata |
| HU-12: hardened CI | Implemented and integrated into develop | Real CI, second-run cache and failing-run artifact evidence |
| HU-13: repository scanning | Implemented and integrated into develop | Real CodeQL/dependency-review execution |
| HU-14: release pipeline/settings script | Implemented and integrated into develop | Approved remote setup, publisher, rehearsal and release |
| HU-15: HTML name/path | 6/6 implementation tasks verified | Review, commit/integration and archive |
| HU-16: exact library coverage | 16/16 implementation tasks verified | Review, commit/integration and archive |

`develop` and the current branch HEAD point to `69c85fd`. The active branch is
`feature/us-9-security`; its working tree also contains the uncommitted HU-15 and
HU-16 changes. Their feature branch names are not committed snapshots of those
changes. `main` still points to the initial `fcb852b` commit. No Git remote is
configured, and no GitHub/PyPI publication or remote settings application has
been performed.

Already integrated merges: HU-8 `1c778a4`, HU-12 `3f78906`, HU-13 `662932f`,
HU-14 `69c85fd`. New commits/merges, pushes, tags, external settings and publication
remain subject to explicit maintainer instructions.

## OpenSpec tracking

OpenSpec planning is local and git-ignored. Implementation progress is distinct
from complete planning artifacts and from release/integration completion.

| Change | Checked tasks | Pending |
| --- | ---: | --- |
| `add-behave-hive-mvp` | **64/66** | 10.3 real CI and 10.5 approved repository publication |
| `harden-and-polish-behave-hive` | **19/42** | 3.9 review, HU-10, HU-11 and final closure/integration |
| `add-github-actions-pipeline` | **18/24** | Settings/publisher, Trello/integration closure and real CI/release runs |
| `configure-html-report-name` | **6/6** | Review/integration/archive follow-up |
| `reach-full-library-coverage` | **16/16** | Review/integration/archive follow-up |

MVP 7.2 and 9.1 were reconciled with the verified uv installation and the full
624-test run with the maintainer's confirmation on 2026-10-18. They are no longer
pending. No change has been archived.

## Pending backlog

- [ ] **HU-9 review:** enable `/security-review` and `/code-review`, or obtain
  approval for an equivalent method. Neither review has been performed or waived.
- [ ] **HU-10:** share file discovery/background pairing and test helpers;
  extract/split execution, expansion and merge; package the HTML template;
  remove temporary C901 exceptions; complete the `/simplify` review.
- [ ] **HU-11:** Allure attachments and `environment.properties`; worker/batch
  metadata; run context, wall/scenario time and speedup; failure-first/opened
  scenarios, summary/copy control, log references, outline groups and URL filters;
  diagnostics E2E tests and documentation.
- [ ] **Integration:** review and commit/integrate HU-9, HU-15 and HU-16 when
  requested, preserving all current working-tree changes.
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
