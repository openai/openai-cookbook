# Understand the public API requirements

The [adapter](../src/admin-api.mjs) uses the public ChatGPT Admin API at `https://api.chatgpt.com/v1`. Supply a workspace-scoped ChatGPT Admin key through the caller. The adapter keeps the key out of saved state and logs. API Platform inference keys cannot authenticate these requests.

The request and response mappings were checked against the [public OpenAPI specification](https://chatgpt.com/public/admin/api-reference/openapi.json) on September 20, 2026. For access setup, see [Managing Admin keys](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/).

| Operation | Public route after `/v1` | Key permission |
| --- | --- | --- |
| Workspace identity and settings | `GET /manage/workspaces/{workspace_id}/usage_limits/workspace` | `chatgpt.enterprise.usage_limit.read` |
| Original override and inherited source | `GET /manage/workspaces/{workspace_id}/usage_limits/users/{user_id}` | Same read permission |
| Current usage and billing unit | Same user route plus `/monthly-usage` | Same read permission |
| Set or restore a user override | `PATCH /manage/workspaces/{workspace_id}/usage_limits/users/{user_id}` | `chatgpt.enterprise.usage_limit.write` |
| Capture current members or resolve an exact email | `GET /manage/workspaces/{workspace_id}/users` | `chatgpt.enterprise.user.read` |
| Verify an enrolled member | `GET /manage/workspaces/{workspace_id}/users/{user_id}`, followed by an active-member lookup | Same user read permission |
| Resolve a workspace group | `GET /manage/workspaces/{workspace_id}/groups/{group_id}` and the same route plus `/users` | `chatgpt.enterprise.directory.read` |
| Observed daily history | `GET /analytics/workspaces/{workspace_id}/usage` | `enterprise.analytics.usage.read` |

Use only the permissions needed by the chosen pattern. Fixed budget release uses the usage-limit and membership routes. Obtain approval before creating a key or enabling writes through the live walkthrough.

## Review snapshots and restoration

`readSnapshot(userId)` returns `workspaceId`, `userId`, `unit`, decimal-string `usage`, a normalized `cap`, the raw `settings`, and `observedAt`. Settings include the original override, effective rule and source, and inherited rule and source. Keep these private in the durable journal. The adapter checks workspace and account-user identity and compares settings across reads.

Restoration preserves three distinct cases:

- **Inheritance:** clear the override with `null` to preserve inheritance.
- **Permanent override:** restore its original finite or unlimited rule, preserving the original tagged or legacy credit representation.
- **Temporary override:** restore it only while its saved expiry equals the approved current period end. The API computes the expiry when it receives `temporary: true`. Caller-supplied expiry timestamps are unsupported.

Multiple override rules, unknown rule fields, inconsistent source information, or a billing-unit change stop the example. Readback compares amount, expiry, override status, and source identifiers. It treats equivalent decimal formatting and `null` or an empty override array as unchanged.

`setCap` sends one absolute tagged amount. The engine supplies the expected settings to detect newly observed edits; initial reductions also supply expected usage. Mutations stop within 30 seconds of the approved period end. The API exposes no conditional-write token, so another administrator can edit between the last read and PATCH. Coordinate one writer and stop on conflicting readback.

Timeouts, unreadable successful write responses, and write-side server errors require reconciliation. The adapter leaves PATCH retries to the controller. It surfaces HTTP status and `Retry-After` and excludes error bodies from saved state.

## Review membership and usage history

Member capture follows `after=last_id` until `has_more` is false and returns sorted IDs. The endpoint excludes service accounts and is eventually consistent. Email selectors use the exact email filter and require one matching active member. Group selectors verify workspace ownership, follow the group-user cursor through every page, and include active users. Explicit IDs, resolved emails, and group members form one deduplicated list. Missing or ambiguous matches stop capture.

The reviewed enrollment saves the resolved IDs and their email/group matches. Later arrivals require a new enrollment. Each run checks those matches before processing; a changed match stops new grants. Restoration uses the saved IDs. Before a write, the adapter verifies the individual workspace member and active status. A member without an email requires an active-directory lookup.

`apiLimits.maxPages` and `apiLimits.maxRows` set optional bounds for paginated reads. Reaching either bound stops processing; the adapter never treats a partial page set as the complete cohort.

Every captured member must have an explicit effective rule and source in the usage-limit response. The public schema permits a null effective cap with no defined unlimited interpretation or source. That response stops the entire capture with `CAP_SOURCE_UNAVAILABLE`. Review and use an explicitly selected supported cohort, or establish the member's intended effective setting through your normal admin process before capturing everyone again.

History uses UTC-midnight bounds, fetches every page, and selects the enrolled user locally. The public endpoint has no user filter. One adapter instance shares a range read across members for up to 60 seconds, measured from the first page; pagination that exceeds that freshness stops the calculation. Separate AWS workers have separate caches. It reads native `credits` or `cost_usd` and excludes `estimated_cost_usd` from calculations. A second billing unit, missing or duplicate day, unavailable amount, or wrong actor stops the usage-based pattern. Reported zero is accepted. A missing row stops the pattern, including when the API omits an inactive day. Choose fixed budget release when complete daily observations are unavailable.

Returned history is labeled `semantics: "observed"`. Later corrections can change it after all pages have been fetched. The data has no finalization watermark, and the example cannot guarantee exact daily spending.

## Verify before live use

These API responses omit configured usage-period bounds. Independently verify the current period and the counter's scope in Admin Console, including any billing-cycle alignment. See [usage-limit behavior](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu). A low or decreasing counter is insufficient evidence of a reset.

The adapter tests verify request shapes and error handling against synthetic responses. Workspace eligibility, cap enforcement, accepted writes, and cloud delivery require live checks. Use the live walkthrough to verify the intended identity, unit, counter scope, exact before-state, temporary expiry, and restoration in the approved test workspace.
