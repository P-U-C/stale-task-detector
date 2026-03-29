# Review code against spec

Read CLAUDE.md for project conventions.
Read MISTAKES.md for known pitfalls.

Review the code just written. Check:
1. Spec/acceptance criteria — does it do what was asked?
2. CLAUDE.md conventions — named exports, no any, no console.log, correct test location
3. MISTAKES.md patterns — any known mistakes repeated?
4. Security — payment handling, auth, input validation, no hardcoded secrets
5. Edge cases — empty inputs, nulls, timeouts, rate limits, file corruption

Output:
- 🟢 Pass: [what's correct]
- 🟡 Warning: [works but could be better — non-blocking]
- 🔴 Fail: [wrong, must be fixed]

For each 🔴: file path, exact problem, exact fix.
Do NOT fix anything. Review only.
