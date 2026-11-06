{
  "findings": [
    {
      "file": ".github/ci/coverage-modules.mjs",
      "line": 62,
      "severity": "medium",
      "claim": "A policy whose coverage.include is an empty array makes the per-module gate exit 0 with no output and check no module.",
      "failure_scenario": "Policy {coverage:{lines:85,branches:85,statements:0,include:[]}} with a valid report. Array.isArray([]) is true, so the script takes the slicing path. include.forEach runs zero times, code stays 0, and run() returns 0 printing nothing. Any module below the floor goes green, and nothing in the output shows that zero modules were checked. The checker's own `if (include.length)` guard is skipped for the same input. Only the policy file can trigger this, not the report. I read the code and did not run it."
    }
  ]
}
