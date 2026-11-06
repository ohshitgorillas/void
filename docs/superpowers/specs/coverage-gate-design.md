Status: approved.

## Why

The 85% lines-and-branches floor must hold for each of the 7 fork-owned modules, and nothing in the tree compares a figure per module:

- Cadence's checker reads only the report's totals (`~/.claude/plugins/cache/cadence/cadence/3.11.1/cadence-core/templates/coverage-report-check.mjs:59-71`) and prints one line per metric (`:100-115`). The policy's `include` reaches it only as a list of files that must be present in the report (`:72-80`).
- The accepted pytest command measures `--cov=app` (`.planning/config.json:102`, `.github/cadence/coverage-policy.json:18`): 17 files, 9,899 lines, of which the 7 `include` files hold 1,948. A totals check over that report judges upstream's files, not the fork's.
- `include` already has two homes kept equal by Cadence: `.planning/config.json:91-99` is the source, `.github/cadence/coverage-policy.json:7-15` its rendered mirror, compared key by key by `planning.mjs test-policy check` (`cadence-core/bin/planning/testing-policy.mjs:198-206`). A `.coveragerc` `[report] include`, or a policy file per module, would be a third and an eighth home for the same list and the same thresholds.
- No coverage configuration exists in the tree today (no `.coveragerc`, `setup.cfg`, `pytest.ini`, `tox.ini` or `pyproject.toml` at the root).
- `test-policy check` matches each accepted command as text against the workflow files and checks nothing about its shape (`testing-policy.mjs:222-229`), so a repo-owned command in `testing.coverage.commands` is valid.

The gate keeps `--cov=app` as measured and judges each `include` file on its own slice of the one `coverage.json`, through the unmodified checker, once per file. No upstream file is read, and no total over `app/` is compared.

## Modules

### `.github/cadence/coverage-report-check.mjs`

Cadence's template, copied byte for byte. It holds the floor comparison, the report validation and the absent-file check. It is never edited in this repo.

### `.github/ci/coverage-modules.mjs`

Runs the checker once per `include` file on that file's slice of `coverage.json`, prefixes each output line with the file, and exits 1 if any file fails. Node builtins only (`node:fs`, `node:os`, `node:path`, `node:child_process`), like the checker.

```js
// node .github/ci/coverage-modules.mjs --report coverage.json [--policy .github/cadence/coverage-policy.json]
//
// For each entry of policy.coverage.include, in policy order:
//   <file>: <each line the checker prints, verbatim>
// e.g.  app/gate.py: lines: 91.20% meets 85
//       app/langmark.py: FAIL branches: 70.00% is below 85
// Every file is checked; the run never stops at the first failure. Exit 1 if any file's checker run exits non-zero.

/** coverage.py JSON report -> a report holding only `file`:
 *  { meta: report.meta, totals: report.files[file].summary, files: { [file]: report.files[file] } }.
 *  A file absent from report.files gives
 *  { meta: report.meta, totals: { covered_lines: 0, num_statements: 0, covered_branches: 0, num_branches: 0 }, files: {} },
 *  which the checker fails as absent from the report. */
export function slice(report, file) {}

/** -> { coverage: { ...policy.coverage, include: [file] } }: thresholds, exclude and commands unchanged. */
export function modulePolicy(policy, file) {}

/** The script's whole run; returns the exit code.
 *  - Reads --policy (default `.github/cadence/coverage-policy.json`) and --report.
 *  - An include entry holding any of `*?[{` prints `FAIL <entry>: include entries must be file paths for per-module coverage`
 *    and counts as a failed file.
 *  - A report that does not parse as JSON with a `files` object is passed unsliced, with the real policy, to one checker run,
 *    whose output and exit code are returned as they are.
 *  - Slices and module policies are written under one `fs.mkdtempSync(os.tmpdir() + '/coverage-modules-')` directory,
 *    removed in a `finally`.
 *  - The checker is `../cadence/coverage-report-check.mjs` resolved from this file, run with `process.execPath`,
 *    `--format python --report <slice> --policy <module policy>`, cwd = the repo root, stdout and exit status captured. */
export function run(argv) {}

// Runs `process.exit(run(process.argv))` only when executed directly.
```

Replaces: the checker's single totals verdict over `--cov=app` as the second accepted command.

### `tests/test_coverage_modules.py`

Proves the per-module gate on hand-built reports. `unittest`, like the suite. Runs `node` from `PATH`; a missing `node` fails the test, never skips it.

```python
def run_modules(tmp: Path, files: dict[str, dict], include: list[str]) -> subprocess.CompletedProcess:
    """Writes tmp/coverage.json ({"meta": {"branch_coverage": True}, "totals": <sum of files>, "files": files})
    and tmp/policy.json (lines 85, branches 85, statements 0, the given include, exclude [], commands []),
    runs `node .github/ci/coverage-modules.mjs --report tmp/coverage.json --policy tmp/policy.json`
    with cwd = the repo root, and returns the result with text output."""

def summary(lines: int, covered: int, branches: int, covered_branches: int) -> dict:
    """A coverage.py `files[<f>]` entry with that `summary`."""

class CoverageModules(unittest.TestCase):
    def test_every_module_at_floor_passes(self): ...          # exit 0, one `<f>: lines:` and one `<f>: branches:` meets-line per file
    def test_module_lines_below_floor_fails_naming_it(self): ...
    def test_module_branches_below_floor_fails_naming_it(self): ...
    def test_high_total_hides_no_low_module(self): ...        # totals >= 85, one module below: exit 1, that module named
    def test_module_absent_from_report_fails_naming_it(self): ...
    def test_glob_include_entry_fails(self): ...
    def test_unreadable_report_fails(self): ...
```

The `include` paths used are tracked files (`app/gate.py`, `app/langmark.py`), since the checker confirms them with `git ls-files`.

## Homes

| Concern | Home | Forbidden elsewhere |
|---|---|---|
| Floor and thresholds | `testing.coverage` in `.planning/config.json`, rendered to `.github/cadence/coverage-policy.json` by `planning.mjs test-policy render` | Any threshold in a workflow, a `.coveragerc`, a per-module policy file in the tree, or pytest `--cov-fail-under` / `--fail-under` |
| Which files are judged | `testing.coverage.include`, same home | A `.coveragerc` or `setup.cfg` `[report] include`/`omit`, a `[run] source` narrower than `app`, a file list in `coverage-modules.mjs` or `tests.yml` |
| What is measured | The first accepted command, `--cov=app --cov-branch --cov-report=json` | Any other coverage run or report in CI |
| The floor comparison and report validation | `.github/cadence/coverage-report-check.mjs`, unmodified | Any percentage or threshold comparison in `coverage-modules.mjs` or a workflow step |
| Per-module enforcement | `.github/ci/coverage-modules.mjs` | A totals-only checker step in `tests.yml`; any second per-module step |
| Accepted command text | `testing.coverage.commands` in `.planning/config.json`, rendered | Hand edits to `coverage-policy.json`; a workflow command that is not the accepted text verbatim |

The accepted commands, after render, are exactly:

1. `uvx --with pytest-cov --with-requirements tests/requirements.txt pytest --cov=app --cov-branch --cov-report=json`
2. `node .github/ci/coverage-modules.mjs --report coverage.json`

`coverage.json` and `.coverage` are ignored by `.gitignore`.

### Phase 1 CONTEXT lines this design replaces

In `.planning/phases/1/CONTEXT.md`:

- D-02, replace the sentence "Both accepted commands appear in the workflow verbatim, as separate steps with no `continue-on-error`; only the checker enforces the floor (no pytest `--fail-under`); `coverage.json` is uploaded as an artifact with `if: always()`." with: "Both accepted commands appear in the workflow verbatim, as separate steps with no `continue-on-error`. The floor is compared only by Cadence's checker, which `.github/ci/coverage-modules.mjs` (the second accepted command) runs once per `include` file on that file's slice of `coverage.json`; no pytest `--fail-under`, no `.coveragerc`, no totals-only checker step. `coverage.json` is uploaded as an artifact with `if: always()`."
- D-03, replace "Cadence's `cadence-core/templates/coverage-report-check.mjs` is copied unmodified to `.github/cadence/coverage-report-check.mjs`." with: "Cadence's `cadence-core/templates/coverage-report-check.mjs` is copied unmodified to `.github/cadence/coverage-report-check.mjs`; the workflow never calls it directly, `.github/ci/coverage-modules.mjs` runs it once per `include` file."
- D-04, after "changed in config `testing.coverage.commands` and re-rendered into the policy with `planning.mjs test-policy render`", add: "In the same render, the second accepted command becomes `node .github/ci/coverage-modules.mjs --report coverage.json`. `--cov=app` is unchanged."
- AC3, replace "and the checker prints each of the 7 `include` files at or above 85% lines and 85% branches" with: "and the second command prints, for each of the 7 `include` files, an `<file>: lines: … meets 85` and an `<file>: branches: … meets 85` line".
- AC4, replace the whole line with: "With one fork-owned module's test file removed (e.g. `tests/test_langmark.py`), the two commands exit non-zero and the second command prints a `<file>: FAIL` line naming that module. The module used is one whose figure falls below 85% without its test file; `langmark` is also imported through `app/server.py:43`, so its figure without `tests/test_langmark.py` is unmeasured until the first run."

`.planning/ROADMAP.md` Phase 1 criteria 3 and 4 hold as written: "the report check" in criterion 3 is the second accepted command.

## Order

`implementer` writes `.github/`, `.gitignore` and `.planning/`; `test-writer` writes `tests/`. The roster was not surveyed for `.github/` Writes; the step goes to the roster agent whose Writes holds it if that is not `implementer`.

1. **Checker and per-module runner land.** Copy the template unmodified; build `coverage-modules.mjs` as in **Modules**; add `coverage.json` and `.coverage` to `.gitignore` (lines appended only; the file carries the owner's uncommitted edits). Paths: `.github/cadence/coverage-report-check.mjs`, `.github/ci/coverage-modules.mjs`, `.gitignore`. Agent: `implementer`.
2. **Per-module gate tests.** Paths: `tests/test_coverage_modules.py`. Agent: `test-writer`.
3. **Accepted commands rendered.** Set `testing.coverage.commands` to the two commands under **Homes** and run `planning.mjs test-policy render`. Paths: `.planning/config.json`, `.github/cadence/coverage-policy.json`. Agent: `implementer`.
4. **`tests` workflow.** `.github/workflows/tests.yml` per D-01, D-02, D-05 and D-07, its two coverage steps the two accepted commands verbatim, then the `if: always()` upload of `coverage.json`; `planning.mjs test-policy check --root .` ends at `"gate_found":true`. Paths: `.github/workflows/tests.yml`. Agent: `implementer`.

`tests/requirements.txt` (D-04) and the per-module tests that bring each module to the floor (D-08) are the phase plan's own steps and build on step 4's output; no module test may add a coverage setting, threshold or file list.
