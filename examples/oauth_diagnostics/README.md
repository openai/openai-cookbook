# Diagnose MCP OAuth configuration drift without collecting credentials

An offline draft Cookbook contribution by **Sophia Cole / ColeWorld**.
MIT licensed; see LICENSE. This contribution has not been accepted or endorsed by
OpenAI. No credential access or live integration is included.

## What you will learn

- Separate configured intent, copied public discovery values, and recorded public
  observations instead of treating a successful-looking configuration as a working login.
- Identify issuer, resource, effective callback, scope, endpoint, and client-mode drift.
- Produce a bounded, value-free report suitable for a human or an agent's diagnostic tool.
- Preserve uncertainty: a missing observation is `unknown`, never an inferred success.

The notebook uses synthetic `.test` domains and standard-library code. It makes no
network requests, OAuth attempts, tool calls, SDK calls, or paid model calls. No account
or API key is needed. There is intentionally no live-connection switch.

## Run

Use Python 3.10 or later from this directory:

```sh
python -m unittest -v test_oauth_doctor
```

Open `mcp_connection_doctor.ipynb` and run its cells in order. They import the adjacent
module and fixtures, so start the notebook in this directory. To check the notebook's
format and execute its ordinary Python cells without starting a kernel:

```sh
# Only if nbformat is not already installed in your chosen environment:
python -m pip install -r requirements.txt
python validate_notebook.py
```

The helper validates notebook JSON against nbformat's schema, verifies source cells
have no saved outputs, and executes cells in one shared Python namespace with socket
and DNS entry points stubbed to fail. This is **not** a full Jupyter kernel test,
kernel-transport test, security sandbox, browser test, or live OAuth test. It executes
only this trusted, fixed-name notebook; do not repurpose it for untrusted notebooks.

## Smallest programmatic example

```python
from oauth_doctor import diagnose
from safe_fixtures import matching_evidence

report = diagnose(matching_evidence())
assert report["status"] == "settings_match"
assert report["authentication"] == "not_verified"
assert report["tool_access"] == "not_verified"
```

`diagnose_json(text)` provides the same checks for a JSON string. It rejects duplicate
object keys, nonstandard numeric constants, malformed JSON, and inputs longer than
65,536 characters. Neither entry point reads files, environment variables, or secrets.

## Input contract: public fields, not raw traces

The document is a plain dictionary with up to three sections. Every section and field
is optional because evidence can be incomplete. Omit uncollected fields; `null` is
invalid. Each section must be a plain dictionary. Strings, lists of strings, and the
following exact field names are accepted. Unexpected fields reject the entire document.

**configured** represents the client's intended values for a single authorization attempt:

- `issuer`, `resource`, `redirect_uri`, `authorization_endpoint`, `token_endpoint`: URLs.
- `scopes`: list of case-sensitive public scope names, not a space-joined string.
- `client_type`: `public` or `confidential`.
- `token_endpoint_auth_method`: one of the explicitly supported method names below.

**discovered** contains selected public metadata values, copied by the caller:

- `issuer`, `authorization_endpoint`, `token_endpoint`: authorization-server metadata.
- `resource`: protected-resource metadata. It is not the authorization-server issuer.
- `scopes_supported`: authorization-server scope advertisement, not a grant.
- `token_endpoint_auth_methods_supported`: authorization-server method advertisement.

**observed** describes public values recorded for that same attempt:

- `selected_issuer`: the effective issuer selected by the client, not an unverified JWT claim.
- `authorization_resource`, `token_resource`: resource values used in the respective requests.
- `authorization_redirect_uri`, `token_redirect_uri`: the respective redirect_uri parameters,
  **not** the returned browser callback URL containing a code or state.
- `requested_scopes`, `granted_scopes`: separately recorded public scope sets, if available.
- `client_type`, `token_endpoint_auth_method`: effective client configuration for the attempt.

Supported methods are `none`, `client_secret_basic`, `client_secret_post`,
`private_key_jwt`, `tls_client_auth`, and `self_signed_tls_client_auth`. This is a
deliberately limited profile, not a complete OAuth method registry. A public client
is paired with `none`; a confidential client is paired with an authentication method.
No credential or PKCE operation is tested by that pairing.

List order and duplicates do not matter. `[]` explicitly records an empty scope set;
an absent field means no evidence. The helper does not infer RFC metadata defaults:
an absent copied field might mean it was not collected, rather than omitted by the server.

### Safety boundary

Do not supply HTTP headers, cookies, tokens, authorization codes, PKCE verifiers,
passwords, client secrets, full metadata/response objects, browser callback responses,
or arbitrary logs. Deliberately select public fields before invoking the helper.

The validator rejects unknown/nested fields, URL userinfo, query strings and fragments,
control characters, and several recognizable credential-like patterns. It does **not**
sanitize traces or detect every secret: an arbitrary secret may resemble a valid scope
name or URL path. The caller remains responsible for supplying public values only.
Reports never include supplied values or raw exception messages, even after rejection.
Do not treat a successful validation as proof that the input is safe to store or share.

Limits are intentional: ASCII URLs only; HTTPS except HTTP callback URLs on exactly
`localhost`, `127.0.0.1`, or `[::1]`; no URL query/fragment; no trailing-dot hostnames,
encoded controls/whitespace, backslashes, or nested percent encodings. URLs are bounded
to 2,048 characters, lists to 128 entries, scope/method strings to 128 characters.
Some legitimate OAuth deployments fall outside this profile. Rejection means invalid
**for this recipe**, not necessarily invalid under every OAuth specification. Never
strip disallowed data and pretend it is equivalent.

## Comparison rules and evidence limits

- **Issuer:** exact string equality, including host case and trailing slash. Missing or
  mismatched issuer evidence blocks dependent authorization-server metadata comparisons.
- **Resource:** lowercase only scheme and host for comparison. Preserve path case,
  trailing slash, explicit ports, percent escapes, and dot segments.
- **Effective callback:** exact string equality across configured, authorization-request,
  and token-request values. This does not implement registration matching. In particular,
  native-app loopback registration can permit variable ports; `configured.redirect_uri`
  here means the concrete URI selected for this attempt, not a registration template.
- **Endpoints:** exact comparison of supplied values, conservatively flagging drift rather
  than trying to determine whether differently spelled URLs reach the same server.
- **Scopes:** requested/configured and requested/granted sets are compared for equality.
  A grant difference is a discrepancy to investigate, not proof that OAuth failed.
  Configured scopes absent from an advertisement produce `review`, not an unsupported-scope
  verdict, because an advertisement need not include every supported scope.
- **Client mode:** compare selected types/methods, check the stated profile pairing, and
  compare configured authentication method with the advertised method list.

Each check gives an ID, status, fixed field paths, explanation, and action without echoing
values. Aggregate precedence is `invalid_input`, `mismatch`, `evidence_incomplete`,
`review_required`, then `settings_match`. Inspect individual checks even if a different
issue dominates the aggregate. A complete, matching record still always reports
`authentication: not_verified` and `tool_access: not_verified`.

No metadata provenance, TLS trust, DNS identity, authorization-server selection policy,
client registration, state/PKCE, signatures, token audience, token expiry, consent,
grants, MCP initialization, or tool result is independently verified. Fixes require
reviewing the named fields at their original sources. Any later authenticated runtime
test is a separate, explicitly authorized task outside this recipe.

## Primary references

Protocol references checked on 2026-10-23; the recipe targets the pinned MCP revision
rather than silently adopting future changes.

1. [MCP authorization, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization):
   resource indicators, scheme/host case tolerance, callback matching, and scope guidance.
2. [RFC 8414, sections 2, 3.3, and 4](https://www.rfc-editor.org/rfc/rfc8414.html#section-3.3):
   exact issuer equality, string comparisons, and non-exhaustive scope advertisements.
3. [RFC 8707, section 2](https://www.rfc-editor.org/rfc/rfc8707.html#section-2): resource
   identifiers. Its permitted URI surface is wider than this recipe's safety profile.
4. [RFC 6749, sections 3.1.2.3 and 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3):
   callback and scope semantics, including case-sensitive, order-independent scope names.
5. [RFC 8252, section 7.3](https://www.rfc-editor.org/rfc/rfc8252.html#section-7.3):
   native-app loopback callbacks and their registration-port exception.

## Files and status

- `oauth_doctor.py`: runtime helper, Python standard library only.
- `safe_fixtures.py`: fresh, synthetic public evidence fixtures.
- `test_oauth_doctor.py`: offline behavioral, validation, and no-echo regression tests.
- `mcp_connection_doctor.ipynb`: narrative recipe and runnable examples.
- `validate_notebook.py`: schema and sequential Python-cell verification.
- `requirements.txt`: notebook validation dependency only.
- `VERIFICATION.md`: commands, results, and explicitly unverified layers.

This draft was built and tested offline. Full-kernel execution and final author
review remain pending. Attribution is Sophia Cole / ColeWorld; see LICENSE for the
MIT license.
