# Public API contract and limits

The [adapter](../src/admin-api.mjs) uses the public ChatGPT Admin API at `https://api.chatgpt.com/v1`. It accepts a workspace-scoped Admin key through its caller; it never saves or logs the key. This is separate from an API Platform inference key.

The request and response mappings were checked against the [public OpenAPI specification](https://chatgpt.com/public/admin/api-reference/openapi.json) on September 20, 2026. For access setup, see [Managing Admin keys](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/).

| Operation | Public route after `/v1` | Key permission |
| --- | --- | --- |
| Workspace identity and settings | `GET /manage/workspaces/{workspace_id}/usage_limits/workspace` | `chatgpt.enterprise.usage_limit.read` |
| Original override and inherited source | `GET /manage/workspaces/{workspace_id}/usage_limits/users/{user_id}` | Same read permission |
| Current usage and billing unit | Same user route plus `/monthly-usage` | Same read permission |
| Set or restore a user override | `PATCH /manage/workspaces/{workspace_id}/usage_limits/users/{user_id}` | `chatgpt.enterprise.usage_limit.write` |
| Capture current members | `GET /manage/workspaces/{workspace_id}/users` | `chatgpt.enterprise.user.read` |
| Observed daily history | `GET /analytics/workspaces/{workspace_id}/usage` | `enterprise.analytics.usage.read` |

Use only the permissions needed by the chosen pattern. Fixed budget release does not call analytics. Creating a key and enabling writes require a separately approved live walkthrough.

## Snapshot and restoration

`readSnapshot(userId)` returns `workspaceId`, `userId`, `unit`, decimal-string `usage`, a normalized `cap`, the raw `settings`, and `observedAt`. Settings include the original override, effective rule and source, and inherited rule and source. Keep these private in the durable journal. The adapter checks workspace and account-user identity and compares settings across reads.

Restoration preserves three distinct cases:

- **Inheritance:** clear the override with `null`; do not copy an inherited amount into a new permanent user override.
- **Permanent override:** restore its original finite or unlimited rule, preserving the original tagged or legacy credit representation.
- **Temporary override:** restore it only while its saved expiry equals the approved current period end. The API accepts `temporary: true` and computes the expiry; it does not accept an arbitrary expiry timestamp.

Multiple override rules, unknown rule fields, inconsistent source information, or a billing-unit change stop the example. Readback compares amount, expiry, override status, and source identifiers. Decimal formatting and `null` versus an empty override array do not count as changes.

`setCap` sends one absolute tagged amount. The engine supplies the expected settings to detect newly observed edits; initial reductions also supply expected usage. Mutations stop within 30 seconds of the approved period end. These checks reduce risk but cannot make separate reads and writes atomic: the API exposes no conditional-write token. Another administrator can still edit between the last read and PATCH. Coordinate one writer and stop on conflicting readback.

Timeouts, unreadable successful write responses, and write-side server errors require reconciliation. The adapter never retries a PATCH itself. It surfaces HTTP status and `Retry-After` without storing an error body.

## Membership and history

Member capture follows `after=last_id` until `has_more` is false and returns sorted IDs. The endpoint excludes service accounts and is eventually consistent. A reviewed capture represents those observed members; it does not automatically enroll later arrivals.

Every captured member must have an explicit effective rule and source in the usage-limit response. The public schema also permits a null effective cap but does not define it as an unlimited rule or supply a source. This example stops the entire capture on that response (`CAP_SOURCE_UNAVAILABLE`); it does not silently skip that member. Review and use an explicitly selected supported cohort, or establish the member's intended effective setting through your normal admin process before capturing everyone again.

History uses UTC-midnight bounds, fetches every page, and selects the enrolled user locally. It reads native `credits` or `cost_usd`; it never converts `estimated_cost_usd`. A second billing unit, missing or duplicate day, unavailable amount, or wrong actor stops the usage-based pattern. Reported zero is accepted; a missing row is never filled with zero. Consequently, a genuinely inactive day can prevent this pattern from running if the API omits its row. Fixed budget release is the simpler choice when complete daily observations are unavailable.

Pagination completion is not data finalization. Returned history is explicitly labeled `semantics: "observed"`; later corrections can change it. No watermark or exact daily spending guarantee is claimed.

## Verify before live use

The current API does not return configured usage-period bounds in these responses. Independently verify the current period and the counter's scope in Admin Console, including any billing-cycle alignment. See [usage-limit behavior](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu). A low or decreasing counter alone does not prove a reset.

The included adapter tests use synthetic responses. They verify request shapes and error handling, not workspace eligibility, actual cap enforcement, accepted writes, or cloud delivery. The live walkthrough must verify the intended identity, unit, counter scope, exact before-state, temporary expiry, and restoration in the approved test workspace.
