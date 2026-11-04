# Local verification record

Date: 2026-10-23. Tested with Python 3.12.14 and nbformat 5.11.1.
No packages were installed specifically for this candidate's verification; an existing
notebook-validation environment supplied nbformat. The runtime helper and unit tests
use only the standard library.

## Executed checks

All commands ran from the recipe directory against the final Python implementation.

| Command | Result |
| --- | --- |
| `python -m unittest -v test_oauth_doctor` | Exit 0; 42 tests passed. |
| `python validate_notebook.py` using the environment with nbformat | Exit 0; notebook schema valid; all 8 code cells executed sequentially. |
| `python -m py_compile oauth_doctor.py safe_fixtures.py test_oauth_doctor.py validate_notebook.py` | Exit 0; all four Python files compiled. |

The notebook has 18 total cells. Saved code-cell outputs are empty and execution counts
are null. Sequential-cell verification captures the demonstration output in memory,
does not modify the notebook, and blocks the tested socket/DNS entry points.

## Behavioral evidence

- A complete matching fixture returns `settings_match`, while authentication and tool
  access remain `not_verified` and network activity is `none`.
- Exact issuer, effective callback, and endpoint drift is detected. Missing/mismatched
  issuer evidence prevents dependent metadata checks from being reported as matches.
- Resource normalization changes only scheme/host case; paths, ports, trailing slashes,
  and percent escapes are not conflated.
- Scope order and duplicates are equivalent; case and membership differences matter.
  Missing advertised scopes yield review rather than an unsupported-scope assertion.
- Missing every individual fixture field, in turn, prevents a fully matching report.
  Missing observations remain unknown; explicit empty scope sets are distinct.
- Public/confidential client modes and token endpoint method discrepancies are covered.
- Unexpected fields, nested structures, invalid types, malformed URLs, unsafe URL forms,
  recognizable secret-like inputs, and malicious subclass inputs fail closed.
- JSON duplicate keys, malformed JSON, excessive input length, and nonstandard constants
  are rejected without returning parser text.
- Output tests verify that synthetic secret sentinels and valid input values are not
  echoed. This is not evidence that every possible secret can be detected in input.
- Unit and notebook checks use synthetic fixtures only; no authorized runtime state is
  changed and no source evidence is independently authenticated.

## Not verified

- Full Jupyter kernel execution was not run. The current runtime has a known
  kernel-socket restriction; schema plus sequential Python execution is a distinct,
  narrower check, not a substitute claim of full-kernel execution.
- No live OAuth, network discovery, token exchange, API/SDK/model call, MCP initialization,
  or tool call was performed. No server identity, real authentication, grant, or tool
  permission was established.
- No dedicated linter, type checker, browser rendering test, or other Python version
  was run. The checked Python files compiled successfully.
- No credential creation or paid operation was performed during verification.

## Draft verification conclusion

The offline implementation, synthetic regression suite, notebook schema, and sequential
examples pass their specified checks. Full-kernel execution and live interoperability
remain unverified. This draft has not been accepted or endorsed by OpenAI and is not an
authentication/security certification.
