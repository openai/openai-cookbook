# Understand the public API requirements

The [adapter](../src/admin-api.mjs) uses the public ChatGPT Admin API at `https://api.chatgpt.com/v1`. Supply a workspace-scoped ChatGPT Admin key through the caller. The adapter keeps the key out of saved state and logs. API Platform inference keys cannot authenticate these requests.

The request and response mappings were checked against the [public OpenAPI specification](https://chatgpt.com/public/admin/api-reference/openapi.json) on September 21, 2026. For access setup, see [Managing Admin keys](https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console/).

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

Use only the permissions needed by the chosen pattern. Fixed budget release and individual starting limits use the usage-limit and membership routes. Individual starting limits use current monthly usage and need no analytics history permission. Obtain approval before creating a key or enabling writes through the live walkthrough.

## Check the connection before enrollment

The AWS `check_connection` action tests the deployed runtime's secret and read access before budget configuration or member capture. It uses `GET` requests to verify the workspace, fetch a single member with `users?limit=1`, and read that member's monthly usage to identify the native billing unit. It needs `chatgpt.enterprise.usage_limit.read` and `chatgpt.enterprise.user.read`. The adapter returns only `workspaceId`, `unit`, and `usersRead`; it does not set a cap or capture the roster. Follow [the AWS connection check](aws.md#4-check-the-workspace-connection).

`ADMIN_HTTP_401` means the credential was rejected; `ADMIN_HTTP_403` means access was denied. Check the selected workspace, key status and expiry, and required permissions. These status codes alone do not establish the cause. The check excludes response error bodies and secrets from its result and does not retry authentication failures. Group permissions, usage-history access, individual cap handling, and write access are verified by the later operations that need them.

## Review snapshots and restoration

### Native credits and USD

The user's monthly-usage response identifies its unit with `current_month_usage_unit`. The adapter uses `credit` or `usd` from that response and checks it against the plan's `unit`. The connection check reports the same unit so an admin can choose the matching configuration before enrollment.

Writes carry an explicit unit tag in `limit_amount`. A $50.00 cap uses `{"unit":"usd","amount":"50.00"}`; a 500-credit cap uses `{"unit":"credit","amount":"500"}`. USD caps have cent precision and credit caps use whole credits. Usage arithmetic retains up to six decimal places, rounding finer usage upward; proposed limits round to the next cent or whole credit. The adapter uses native `cost_usd` for USD history and `credits` for credit history. It does not use estimated dollar values from credit usage or apply a conversion rate.

Capture, recurring runs, restoration, and period renewal verify unit consistency. A changed or conflicting unit stops processing for review before a limit update.

### Saved settings

`readSnapshot(userId)` returns `workspaceId`, `userId`, `unit`, decimal-string `usage`, a normalized `cap`, the raw `settings`, and `observedAt`. Settings include the original override, effective rule and source, and inherited rule and source. Keep these private in the durable journal. The adapter checks workspace and account-user identity and compares settings across reads.

Restoration preserves three distinct cases:

- **Inheritance or no configured cap:** clear the override with `null` and verify the original inherited settings or explicit absence of a cap.
- **Permanent override:** restore its original finite or unlimited rule, preserving the original tagged or legacy credit representation.
- **Temporary override:** restore it only while its saved expiry equals the approved current period end. The API computes the expiry when it receives `temporary: true`. Caller-supplied expiry timestamps are unsupported.

Multiple override rules, unknown rule fields, inconsistent source information, or a billing-unit change stop the example. Readback compares amount, expiry, override status, and source identifiers. It treats equivalent decimal formatting and `null` or an empty override array as unchanged.

`setCap` sends one absolute tagged amount. The engine supplies the expected settings to detect newly observed edits. Initial reductions and first writes for individual starting limits also supply expected usage. Mutations stop within 30 seconds of the approved period end. The API exposes no conditional-write token, so another administrator can edit between the last read and PATCH. Coordinate one writer and stop on conflicting readback.

Timeouts, unreadable successful write responses, and write-side server errors require reconciliation. The adapter leaves PATCH retries to the controller. It surfaces HTTP status and `Retry-After` and excludes error bodies from saved state.

## Review membership and usage history

Member capture follows `after=last_id` until `has_more` is false and returns sorted IDs. The endpoint excludes service accounts and is eventually consistent. Email selectors use the exact email filter and require one matching active member. Group selectors verify workspace ownership, follow the group-user cursor through every page, and include active users. Explicit IDs, resolved emails, and group members form one deduplicated list. Missing or ambiguous matches stop capture.

The reviewed enrollment saves the resolved IDs and their email/group matches. Later arrivals require a new enrollment. Each run checks those matches before processing; a changed match stops new grants. Restoration uses the saved IDs. Before a write, the adapter verifies the individual workspace member and active status. A member without an email requires an active-directory lookup.

`apiLimits.maxPages` and `apiLimits.maxRows` set optional bounds for paginated reads. Reaching either bound stops processing; the adapter never treats a partial page set as the complete cohort.

An explicitly absent cap is recorded as `type: "unset"`, with no amount or invented source. This requires a null or empty personal override, explicit null effective and inherited settings, a matching null monthly effective cap, and consistent repeated reads. Missing or contradictory fields stop capture. Imposing a finite cap on an unset setting requires the reviewed initial-reduction opt-in; restoration preserves the saved absence of a cap.

An inherited workspace or group rule can appear as the effective setting before a personal override is installed and as the inherited setting afterward. The adapter compares its amount and full source identity across that change. A changed group ID, amount, or source still stops the write or restoration.

History uses UTC-midnight bounds, fetches every page, and selects the enrolled user locally. The public endpoint has no user filter. One adapter instance shares a range read across members for up to 60 seconds, measured from the first page; pagination that exceeds that freshness stops the calculation. Separate AWS workers have separate caches. It reads native `credits` or `cost_usd` and excludes `estimated_cost_usd` from calculations. A second billing unit, missing or duplicate day, unavailable amount, or wrong actor stops the usage-based pattern. Reported zero is accepted. A missing row stops the pattern, including when the API omits an inactive day. Choose fixed budget release when complete daily observations are unavailable.

Returned history is labeled `semantics: "observed"`. Later corrections can change it after all pages have been fetched. The data has no finalization watermark, and the example cannot guarantee exact daily spending.

## Verify before live use

These API responses omit configured usage-period bounds. Independently verify the current period and the counter's scope in Admin Console, including any billing-cycle alignment. See [usage-limit behavior](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu). A low or decreasing counter is insufficient evidence of a reset.

The adapter tests verify request shapes and error handling against synthetic responses. Workspace eligibility, cap enforcement, accepted writes, and cloud delivery require live checks. Use the live walkthrough to verify the intended identity, unit, counter scope, exact before-state, temporary expiry, and restoration in the approved test workspace.

## Renew a confirmed period

The [AWS renewal helper](aws.md#7-renew-the-next-period) reuses the approved policy and frozen member list after the previous period ends. It reads current membership, native billing units, cap settings, and durable prior state. Every prior member must have a settled state with no pending intent or authorization halt. Changed settings or inherited sources require review.

For `individual_staircase`, renewal derives each new `member.startCap` from the fresh monthly usage snapshot, configured initial headroom, and ceiling. The new enrollment binds those values for review; previous-period starting caps do not carry forward.

An expired temporary override may return to its proven inherited setting. Renewal verifies that transition and preserves the historic settings. If the original restoration target itself expired, the verified current fallback becomes the restoration baseline for the new period. The original record remains archived. Confirm new period dates and counter scope explicitly; neither a lower usage counter nor an old override expiry establishes the next period boundaries.
