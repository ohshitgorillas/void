{
  "findings": [
    {
      "file": ".github/ci/coverage-modules.mjs",
      "line": 59,
      "severity": "medium",
      "claim": "The fix closes only the `include: []` shape. A policy with `coverage.include` missing or non-array (for example `{}`) still makes the gate exit 0 having checked no module.",
      "failure_scenario": "I ran it. Policy {\"coverage\":{\"lines\":85,\"branches\":85,\"statements\":0}} (no include key), and the same with \"include\":{}, plus a valid report whose totals are 100/100 and whose files is {}. `!Array.isArray(include)` sends it down the fallback at lines 59-64. That runs the checker on the whole report, and the checker defaults include to [] (coverage-report-check.mjs:72) and skips its file checks. Output was 'lines: 100.00% meets 85 / branches: 100.00% meets 85', exit 0, with no per-module check and no 'no module was checked' failure. Any module below the floor stays green as long as the report totals pass. The new `include.length === 0` guard at line 69 is never reached for these inputs. Other shapes fail: include:null and include:\"app/gate.py\" both exit 1."
    }
  ]
}
