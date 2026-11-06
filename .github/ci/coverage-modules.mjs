// node .github/ci/coverage-modules.mjs --report coverage.json [--policy .github/cadence/coverage-policy.json]
//
// For each entry of policy.coverage.include, in policy order, runs Cadence's unmodified checker on that file's
// slice of the report and prints each line it prints, prefixed with the file:
//   app/gate.py: lines: 91.20% meets the floor
//   app/langmark.py: FAIL branches: 70.00% is below the floor
// Every file is checked; the run never stops at the first failure. Exit 1 if any file's checker run exits non-zero.
// The floor and the report validation live in the checker and the policy; this script compares nothing itself.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const checker = path.resolve(here, '..', 'cadence', 'coverage-report-check.mjs');
const DEFAULT_POLICY = '.github/cadence/coverage-policy.json';

/** coverage.py JSON report -> a report holding only `file`. A file absent from report.files gives an empty
 *  `files`, which the checker fails as absent from the report. */
export function slice(report, file) {
  const entry = report.files[file];
  if (!entry) {
    return {
      meta: report.meta,
      totals: { covered_lines: 0, num_statements: 0, covered_branches: 0, num_branches: 0 },
      files: {},
    };
  }
  return { meta: report.meta, totals: entry.summary, files: { [file]: entry } };
}

/** -> the policy with `include` narrowed to `file`: thresholds, exclude and commands unchanged. */
export function modulePolicy(policy, file) {
  return { coverage: { ...policy.coverage, include: [file] } };
}

function check(args) {
  const r = spawnSync(process.execPath, [checker, '--format', 'python', ...args], { cwd: root, encoding: 'utf8' });
  const out = (r.stdout || '') + (r.error ? `FAIL checker: ${r.error.message}\n` : '');
  return { out, status: r.status === 0 ? 0 : 1 };
}

const flag = (argv, name) => {
  const i = argv.indexOf(name);
  return i > 0 ? argv[i + 1] : undefined;
};

/** The script's whole run; returns the exit code. */
export function run(argv) {
  const reportArg = flag(argv, '--report');
  const reportPath = reportArg && path.resolve(reportArg);
  const policyPath = path.resolve(flag(argv, '--policy') || path.join(root, DEFAULT_POLICY));

  let report;
  let policy;
  try { report = JSON.parse(fs.readFileSync(reportPath, 'utf8')); } catch { report = undefined; }
  try { policy = JSON.parse(fs.readFileSync(policyPath, 'utf8')); } catch { policy = undefined; }

  const include = policy && policy.coverage && policy.coverage.include;
  if (!report || typeof report.files !== 'object' || report.files === null || !Array.isArray(include)) {
    // nothing to slice: the checker alone judges the report and the policy as given
    const { out, status } = check([...(reportPath ? ['--report', reportPath] : []), '--policy', policyPath]);
    process.stdout.write(out);
    return status;
  }

  if (include.length === 0) {
    console.log('FAIL policy: coverage.include is empty, so no module was checked');
    return 1;
  }

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'coverage-modules-'));
  let code = 0;
  try {
    include.forEach((file, i) => {
      if (/[*?[{]/.test(file)) {
        console.log(`FAIL ${file}: include entries must be file paths for per-module coverage`);
        code = 1;
        return;
      }
      const slicePath = path.join(tmp, `report-${i}.json`);
      const policyOut = path.join(tmp, `policy-${i}.json`);
      fs.writeFileSync(slicePath, JSON.stringify(slice(report, file)));
      fs.writeFileSync(policyOut, JSON.stringify(modulePolicy(policy, file)));
      const { out, status } = check(['--report', slicePath, '--policy', policyOut]);
      for (const line of out.split('\n').filter((l) => l !== '')) console.log(`${file}: ${line}`);
      if (status !== 0) code = 1;
    });
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  return code;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  process.exit(run(process.argv));
}
