# Manage Google Drive access with the ChatGPT Admin API

ChatGPT workspace administrators can choose which Google shared drives the
Google Drive app may access and configure My Drive access separately. This
example previews and updates those settings through the ChatGPT Admin API.

The [administration script](google_drive_access_admin.py) uses only the Python
standard library. It accepts shared-drive IDs or root URLs, imports CSV/text
files, and supports replacing, adding to, or removing from a selected-drive
allowlist.

> **Availability:** This example targets the Google Drive access-policy Admin
> API. Confirm that the endpoint and Google Drive policy enforcement are
> enabled for your workspace before relying on a policy to restrict access.
> A successful policy read or save alone does not establish that enforcement
> is active.

## Understand the policy

All operations use this URL, where `<workspace-id>` is your ChatGPT workspace UUID:

```text
https://api.chatgpt.com/v1/manage/workspaces/<workspace-id>/google-drive/drive-access/allow-list
```

| Method | Behavior |
| --- | --- |
| `GET` | Read the shared-drive allowlist and My Drive setting. |
| `PUT` | Replace the shared-drive allowlist; optionally update My Drive. |
| `DELETE` | Allow all shared drives; preserve the current My Drive setting. |

Every `PUT` requires `drive_ids`. Its three possible states have different meanings:

| `drive_ids` | Shared-drive access |
| --- | --- |
| `null` | All shared drives permitted by the user's Google permissions. |
| `[]` | No shared drives. |
| `["0AExampleFinanceDrive"]` | Only the listed shared drives, subject to Google permissions. |

`allow_personal_drive` is a separate boolean. Omit it, or send `null`, to preserve
the setting observed by the server. Its default is `true`. Setting it to `false`
blocks files outside shared drives, including files shared from another user's
My Drive. To block both categories, use `drive_ids: []` and
`allow_personal_drive: false` together.

The API supports whole shared drives, with at most 1,000 IDs per request. IDs
are case sensitive and contain 5–512 ASCII letters, digits, underscores, or
hyphens. The script deduplicates IDs before sending them. The API does not
resolve names or URLs, verify that IDs exist, grant Google permissions, or
support drive exclusion lists or individual file/folder policies.

## Set up credentials

You need Python 3.10 or later, your workspace UUID, and a ChatGPT workspace
Admin API key with administrator permissions in the workspace's organization.
All three methods, including `GET`, require `chatgpt.enterprise.apps.write`.

In the ChatGPT Admin Console, select your workspace, open **Credentials**, and
choose the **Admin keys** tab. Create a key with **Restricted** permissions and
set **Apps** to **Write**. An OpenAI API Platform key cannot replace this
workspace Admin API key.

In Bash, prompt for the key without putting its value in shell history:

```bash
read -r -s -p "ChatGPT workspace admin key: " CHATGPT_ADMIN_TOKEN
echo
export CHATGPT_ADMIN_TOKEN

export WORKSPACE_ID="<workspace-id>"
```

Replace `<workspace-id>` with your workspace UUID. Run the administration
commands below from `examples/chatgpt/google_drive_access` in a checkout of this
repository. No third-party Python packages are required.

### Optional Google Drive credential

The `inspect` command and any command using root URLs also require
`GOOGLE_DRIVE_TOKEN`. Obtain a Google OAuth access token with the
`https://www.googleapis.com/auth/drive.readonly` scope, using your organization's
approved OAuth application with the Google Drive API enabled. The token's user
must be able to read the shared drives' metadata. See Google's
[OAuth setup guide](https://developers.google.com/workspace/drive/api/quickstart/python#authorize_credentials_for_a_desktop_application)
for an example credential setup.

If you adapt that quickstart, request `drive.readonly` instead of its sample
`drive.metadata.readonly` scope and authorize again after changing scopes.
Supply the resulting access token, rather than a client secret or refresh token.
The administration script does not obtain or refresh Google tokens.

```bash
read -r -s -p "Google Drive access token: " GOOGLE_DRIVE_TOKEN
echo
export GOOGLE_DRIVE_TOKEN
```

The script uses Google's
[`drives.get` method](https://developers.google.com/workspace/drive/api/reference/rest/v3/drives/get)
to verify a shared-drive ID and retrieve its name. It does not request domain
administrator access. Names appear only in inspection and preview output; the
ChatGPT policy receives IDs. ID-only policy commands do not require a Google
token and perform syntax validation only.

## Inspect shared drives

Select a shared drive in Google Drive and copy the URL of its root. Replace the
illustrative ID below with your drive's actual ID:

```bash
python3 google_drive_access_admin.py inspect \
  --drive-url https://drive.google.com/drive/folders/0AExampleFinanceDrive
```

URLs containing an account index, such as `/drive/u/0/folders/ID`, are also
accepted. A folder URL can look like a drive-root URL, so the script validates
the extracted ID with `drives.get`. It rejects an ordinary folder instead of
expanding the request to its containing shared drive. You can also inspect an
ID directly with `--drive-id`. Inspection calls only Google and does not require
the ChatGPT Admin API key.

## Read the current policy

```bash
python3 google_drive_access_admin.py list --workspace-id "$WORKSPACE_ID"
```

A policy allowing selected shared drives while blocking My Drive looks like:

```json
{
  "object": "workspace.google_drive.access_policy",
  "allow_list": ["0AExampleFinanceDrive", "0AExampleResearchDrive"],
  "allow_personal_drive": false
}
```

The response field is `allow_list`; the request field is `drive_ids`.

## Prepare and replace an allowlist

Create `drives.csv` with a `drive_id` column:

```csv
drive_id
0AExampleFinanceDrive
0AExampleResearchDrive
```

Replace these sample IDs with actual shared-drive IDs. A CSV with a `drive_url`
column also works; use exactly one of these two columns. A text file may contain
one ID or root URL per line. Blank lines, text-file comments starting with `#`,
and CSV rows without a value in the chosen column are ignored. An empty input
cannot replace the policy; use the explicit `block-all` command for that intent.

Preview a replacement that also blocks My Drive:

```bash
python3 google_drive_access_admin.py replace \
  --workspace-id "$WORKSPACE_ID" \
  --drives-file drives.csv \
  --my-drive block \
  --dry-run
```

The preview prints the current and proposed policies, resolved drives, HTTP
method, and request body. It reads the current policy and verifies any supplied
URLs without writing. Review the result, then run the same command without
`--dry-run` to send:

```http
PUT /v1/manage/workspaces/<workspace-id>/google-drive/drive-access/allow-list
Authorization: Bearer <CHATGPT_ADMIN_TOKEN>
Content-Type: application/json

{
  "drive_ids": ["0AExampleFinanceDrive", "0AExampleResearchDrive"],
  "allow_personal_drive": false
}
```

This replaces the full shared-drive allowlist. Omit `--my-drive` to preserve its
observed setting. You can supply repeated `--drive-id` or `--drive-url` options
instead of a file, or combine them with a file.

## Add or remove selected drives

For an existing finite allowlist, the script reads it, computes the union or
difference, and sends one replacement `PUT`:

```bash
python3 google_drive_access_admin.py add \
  --workspace-id "$WORKSPACE_ID" \
  --drive-id 0AExampleOperationsDrive \
  --dry-run

python3 google_drive_access_admin.py remove \
  --workspace-id "$WORKSPACE_ID" \
  --drive-id 0AExampleFinanceDrive \
  --dry-run
```

Remove `--dry-run` after review. Removing the final selected drive blocks every
shared drive and requires `--yes`. Adding a duplicate or removing an absent ID
leaves the policy unchanged, unless you also change My Drive.

When `allow_list` is `null`, both `add` and `remove` stop: all shared drives are
already allowed, and the API has no exclusion-list operation. Use `replace` to
select a finite set. To remove an inaccessible drive, supply its known ID
directly; URL verification requires Google access to that drive.

## Change My Drive access

To change My Drive while carrying forward the observed shared-drive policy:

```bash
python3 google_drive_access_admin.py set-my-drive \
  --workspace-id "$WORKSPACE_ID" \
  --my-drive block \
  --dry-run
```

Review and remove `--dry-run` to apply. Use `--my-drive allow` to allow My Drive.
The request includes the observed shared-drive IDs because `PUT` requires
`drive_ids`, even when only My Drive is changing.

## Block or restore shared-drive access

Preview blocking all shared drives and My Drive together:

```bash
python3 google_drive_access_admin.py block-all \
  --workspace-id "$WORKSPACE_ID" --my-drive block --dry-run
```

To apply, replace `--dry-run` with `--yes`. Without `--my-drive`, this command
blocks shared drives while preserving the observed My Drive setting.

To remove the shared-drive restriction, preview `reset`:

```bash
python3 google_drive_access_admin.py reset \
  --workspace-id "$WORKSPACE_ID" --dry-run
```

Replace `--dry-run` with `--yes` to send `DELETE`. Reset sets `allow_list` to
`null` and preserves My Drive. It does not reset My Drive to its default.
Commands whose proposed policy already matches the read policy skip the write.

## Coordinate writes and handle errors

Run one administrator's update at a time. This endpoint has no version
precondition or guaranteed conflict detection. A concurrent save can overwrite
changes to these controls or other Google Drive app settings. A dry run is a
preview, not a reservation; applying the command reads the policy again.
Keep the app's enabled/disabled state in mind: saving a policy does not enable
a disabled Google Drive app.

The example retries `GET` requests up to twice after transient network errors or
HTTP 429, 502, 503, or 504. It sends each `PUT` or `DELETE` only once and provides
no idempotency-key option. After an ambiguous write failure, run `list`, inspect
the current state, and reconcile your intended change before retrying.

| Error | What to check |
| --- | --- |
| HTTP 401 or 403 | Admin key, `chatgpt.enterprise.apps.write`, administrator permissions, workspace organization, and feature availability. For Google requests, check the Google token and drive access. |
| HTTP 404 | Workspace ID or shared-drive ID. A folder ID is not a shared-drive ID. |
| HTTP 400 | Request fields, ID format, and the 1,000-entry limit. |
| HTTP 409 | Read the current policy and review conflicting changes before retrying. Concurrent saves do not always produce this error. |
| HTTP 429 | Wait before retrying a write, then inspect the current policy. |
| HTTP 503 | The Google Drive policy capability may be unavailable or a service may be temporarily unavailable. Confirm workspace support if it persists. |

## Run the offline tests

From the repository root:

```bash
python3 -B -m unittest discover \
  -s examples/chatgpt/google_drive_access \
  -p 'test_*.py' -v
```

The tests mock Google Drive and the ChatGPT Admin API. They require no
credentials and make no live requests.
