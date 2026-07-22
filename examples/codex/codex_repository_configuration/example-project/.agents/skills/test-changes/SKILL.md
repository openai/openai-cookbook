---
name: test-changes
description: Run the smallest relevant test after JavaScript changes. Use when implementation work is ready for verification.
---

1. Inspect the changed files and identify the closest test.
2. Run `scripts/run-tests.sh` from this skill directory.
3. If the test fails, report the failing assertion before changing code.
4. Report the exact command, result, and any behavior that remains untested.
5. Do not commit or push as part of this skill.
