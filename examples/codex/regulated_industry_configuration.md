# Configure Codex for regulated industries

Financial services, healthcare, public-sector, and other regulated teams need a clear answer to a practical deployment question: which Codex settings are enforceable, which are only defaults, and how do those controls differ between macOS and Windows?

This cookbook provides complete starter configurations for Codex `0.138.0` or later. The examples restrict filesystem access to an approved local workspace, disable command-network access, reject user-approved sandbox escalation, and show how to deploy equivalent controls on macOS and native Windows.

These examples are a technical starting point. They are not a compliance certification, a legal interpretation, or a substitute for operating-system permissions, endpoint security, identity controls, data-governance policy, or an organization-specific threat model.

## Understand the two configuration layers

Codex uses two different configuration layers:

| File | Purpose | Can a user override it? | Use it for |
| --- | --- | --- | --- |
| `requirements.toml` | Enterprise-managed requirements. | Supported constraints are enforced and cannot be overridden by user configuration. | Allowed permission profiles, approval policies, managed features, approved MCP servers, and Windows sandbox requirements. |
| `config.toml` | User or device configuration. | Yes, unless a corresponding enterprise requirement constrains the setting. | Recommended defaults, authentication preferences, credential storage, local history, telemetry, and platform-specific client settings. |

Managed defaults from `managed_config.toml` or mobile device management (MDM) configure the starting state, but do not replace enforced requirements. Use the [managed configuration documentation](https://learn.chatgpt.com/docs/enterprise/managed-configuration) to confirm the exact precedence for the clients and deployment method in your fleet.

The managed permission-profile controls in this cookbook require Codex `0.138.0` or later. Clients running `0.137.0` or earlier do not enforce `allowed_permission_profiles` or managed `default_permissions`. Upgrade every supported local desktop, CLI, or IDE client before assigning a policy that depends on those controls. Remote or cloud-hosted execution environments need their own separately verified controls.

## Define the security boundary first

The reference configuration makes the following choices:

- Only a named enterprise-managed permission profile is selectable.
- Commands can read the selected workspace and the minimal operating-system paths needed to run common tools.
- Commands can modify files inside the workspace, except for protected metadata and explicitly denied secret-bearing files.
- Commands cannot use the network.
- Users cannot approve an operation that would execute outside the configured sandbox.
- Browser use, computer use, apps, automatic approval review, unapproved Model Context Protocol (MCP) servers, and remote control are disabled.
- Native Windows devices must use the stronger `elevated` sandbox implementation.

This boundary is intentionally restrictive. Review the workflow impact before rolling it out to a full organization.

> A workspace is trusted by definition. If a user opens a network share as the workspace, that share becomes a workspace root. Use endpoint, identity, or operating-system policy to restrict which directories can become approved workspaces.

## Start with the general enterprise blueprint

The complete cross-platform starter files are:

- [Enterprise requirements](regulated_industry_configuration/requirements.toml)
- [Client configuration](regulated_industry_configuration/config.toml)

The general pair explains the shared control model. For native Windows, deploy the complete Windows-specific pair below so the managed policy also requires the elevated sandbox implementation.

### Enforce the enterprise policy

The managed requirements select one profile, disable escalation approvals and web search, and deny configurable MCP servers until an organization explicitly approves one:

```toml
allowed_approval_policies = ["never"]
allowed_approvals_reviewers = ["user"]
allowed_web_search_modes = ["disabled"]
default_permissions = "regulated_workspace"
allow_managed_hooks_only = true
allow_appshots = false
mcp_servers = {}

[allowed_permission_profiles]
regulated_workspace = true
```

The explicit empty `mcp_servers` table blocks configurable MCP servers. If the table is omitted, MCP servers are not constrained by this requirement. Add a server only after the security team verifies its exact name, identity, data access, and approval model.

The managed profile grants read access to essential runtime paths and limits the writable area to the current workspace:

```toml
[permissions.regulated_workspace]
description = "Edit an approved local workspace without broad filesystem reads."

[permissions.regulated_workspace.filesystem]
":minimal" = "read"
glob_scan_max_depth = 6

[permissions.regulated_workspace.filesystem.":workspace_roots"]
"." = "write"
".git" = "read"
".codex" = "read"
".agents" = "read"
".devcontainer" = "read"
".env" = "deny"
".env.local" = "deny"
"**/.env" = "deny"
"**/.env.*" = "deny"
"**/*.env" = "deny"
"**/*.key" = "deny"
"**/*.pem" = "deny"
"**/*.p12" = "deny"
"**/*.pfx" = "deny"

[permissions.regulated_workspace.network]
enabled = false
```

The profile does not extend the built-in `:workspace` profile because that profile includes broader filesystem reads. Instead, it explicitly grants `:minimal` and the selected `:workspace_roots`. The recursive deny patterns set a bounded scan depth for platforms that pre-expand filesystem matches. On Windows and other platforms that use bounded expansion, files below the configured depth may not be covered. Inspect repository nesting and raise the limit or enumerate protected paths before deployment.

On Windows, deny globs are expanded against files that already exist when the sandbox initializes. The explicit `.env` and `.env.local` entries also protect those known paths if they do not exist yet, but newly created files that match only a glob may not receive the same protection. Keep sensitive files outside approved workspaces when possible and enforce operating-system access controls.

`".git" = "read"` prevents Codex from modifying Git metadata directly. In this strict operating model, repository commits, pushes, and pull-request merges remain human-controlled steps outside Codex.

The full requirements file also disables optional high-risk features and blocks common destructive, infrastructure-changing, and data-transfer command prefixes. Prefix rules are defense in depth, not a complete semantic inspection of shell scripts.

Disabled profile networking applies to sandboxed commands. It does not disable the Codex client's authenticated connection to model services, login, or enterprise configuration. Govern those client connections through the organization's approved proxy, identity, and egress controls.

### Set matching client defaults

The corresponding `config.toml` selects the same permission profile and approval model:

```toml
approval_policy = "never"
approvals_reviewer = "user"
default_permissions = "regulated_workspace"
web_search = "disabled"
allow_login_shell = false

forced_login_method = "chatgpt"
cli_auth_credentials_store = "keyring"
mcp_oauth_credentials_store = "keyring"

[apps._default]
enabled = false
destructive_enabled = false
open_world_enabled = false

[feedback]
enabled = true

[history]
persistence = "none"

[shell_environment_policy]
inherit = "core"
ignore_default_excludes = false
exclude = ["*PASSWORD*", "*CREDENTIAL*", "*PRIVATE*"]

[otel]
environment = "regulated"
log_user_prompt = false
```

`approval_policy = "never"` means Codex cannot ask a user to approve an action that needs additional sandbox permissions. It does not mean Codex never acts: operations already permitted by the active profile can continue without an approval prompt.

`cli_auth_credentials_store = "keyring"` and `mcp_oauth_credentials_store = "keyring"` require the operating-system credential store. A device without a functioning credential store needs an approved deployment-specific alternative.

`history.persistence = "none"` reduces local retention of session history. It can also make later incident reconstruction harder. Configure an approved audit or telemetry destination if your retention policy requires one, and do not enable raw prompt logging unless that data collection has been explicitly approved.

Settings that appear only in `config.toml` remain client defaults unless another supported enterprise requirement or external control enforces them. For this Codex `0.138.0` baseline, treat credential-storage preferences, local history, login-shell behavior, telemetry choices, and Windows private-desktop configuration as defaults that still require device-management review.

The supplied files intentionally do not contain an example workspace UUID, MCP URL, API token, telemetry collector URL, or other organization-specific identifier. Add only verified values from your own environment.

## Deploy the macOS blueprint

Use these complete files for macOS:

- [macOS requirements](regulated_industry_configuration/requirements.macos.toml)
- [macOS client configuration](regulated_industry_configuration/config.macos.toml)

macOS uses the native operating-system sandbox to enforce the resolved permission profile. The macOS example also blocks common remote-transfer commands such as `scp`, `sftp`, `rsync`, and `ssh` through managed command rules.

### Option 1: Install managed requirements as a system file

From the cookbook repository root:

```bash
BLUEPRINT_DIR="examples/codex/regulated_industry_configuration"

sudo install -d -m 0755 /etc/codex
sudo install -m 0644 \
  "$BLUEPRINT_DIR/requirements.macos.toml" \
  /etc/codex/requirements.toml

mkdir -p "$HOME/.codex"
install -m 0600 \
  "$BLUEPRINT_DIR/config.macos.toml" \
  "$HOME/.codex/config.toml"
```

For centrally managed defaults, deploy the same configuration content to `/etc/codex/managed_config.toml` through your device-management workflow. Keep the enforced policy in the requirements layer.

### Option 2: Distribute the policy through macOS MDM

The macOS managed-preferences domain is `com.openai.codex`. It supports these payload keys:

- `requirements_toml_base64` for enterprise-enforced requirements.
- `config_toml_base64` for managed defaults.

Prepare the requirements payload without line wrapping:

```bash
base64 -i \
  examples/codex/regulated_industry_configuration/requirements.macos.toml \
  | tr -d '\n'
```

Prepare the defaults payload separately:

```bash
base64 -i \
  examples/codex/regulated_industry_configuration/config.macos.toml \
  | tr -d '\n'
```

Install each payload under the corresponding managed-preferences key through the organization's existing MDM product. Do not include secrets in either payload.

## Deploy the native Windows blueprint

Use these complete files for native Windows:

- [Windows requirements](regulated_industry_configuration/requirements.windows.toml)
- [Windows client configuration](regulated_industry_configuration/config.windows.toml)

The Windows managed requirements add a platform-specific constraint:

```toml
[windows]
allowed_sandbox_implementations = ["elevated"]
```

The Windows client selects that implementation and keeps private-desktop isolation enabled:

```toml
[windows]
sandbox = "elevated"
sandbox_private_desktop = true
```

`elevated` describes the Windows sandbox implementation and its setup. It does not grant the agent unrestricted administrator privileges. This implementation uses dedicated lower-privilege sandbox users, filesystem boundaries, and firewall rules. Setup can require an administrator to approve local user creation, firewall configuration, or other endpoint-policy changes.

The enterprise requirement prevents a user from falling back to the weaker `unelevated` implementation. If the elevated sandbox cannot be initialized, work with endpoint administrators to resolve the setup issue before enabling the profile.

### Install the Windows files

From an approved administrative PowerShell session at the cookbook repository root:

```powershell
$blueprintDirectory = Join-Path `
    (Get-Location) `
    "examples\codex\regulated_industry_configuration"

$managedDirectory = Join-Path $env:ProgramData "OpenAI\Codex"
$userDirectory = Join-Path $env:USERPROFILE ".codex"

New-Item -ItemType Directory -Path $managedDirectory -Force
New-Item -ItemType Directory -Path $userDirectory -Force

Copy-Item `
    (Join-Path $blueprintDirectory "requirements.windows.toml") `
    (Join-Path $managedDirectory "requirements.toml")

Copy-Item `
    (Join-Path $blueprintDirectory "config.windows.toml") `
    (Join-Path $userDirectory "config.toml")
```

Deploy the files through endpoint-management tooling when possible. The Windows system requirements path is `%ProgramData%\OpenAI\Codex\requirements.toml`; the user configuration path is `%USERPROFILE%\.codex\config.toml`.

### Understand the network-share boundary

On native Windows, the older `read-only` and `workspace-write` sandbox modes can provide broader filesystem read access than a regulated organization expects. A user approval can also authorize a specific operation outside a normal sandbox when the selected approval policy permits it.

The Windows blueprint addresses those risks by combining:

1. A managed custom profile that grants only minimal runtime reads and the selected workspace.
2. An enterprise allowlist that prevents selecting broader built-in profiles.
3. `approval_policy = "never"`, which blocks user-approved sandbox escalation.
4. A mandatory elevated Windows sandbox implementation.
5. Disabled network access for sandboxed commands.

Do not rely on `[permissions.filesystem].deny_read` alone to block access to Windows network shares. Managed `deny_read` applies to direct file tools on native Windows, but shell subprocess reads do not use that same requirement. The explicit managed permission profile and elevated sandbox address a different control layer.

Also keep the underlying Server Message Block (SMB) permissions, endpoint policy, execution identity, and network segmentation aligned with the same security goal. A network share selected as the workspace is inside the profile's workspace boundary, so an organization that prohibits network-share workspaces needs an external control that prevents that selection.

## Compare deployment locations

| Configuration layer | macOS | Native Windows |
| --- | --- | --- |
| Enforced system requirements | `/etc/codex/requirements.toml` | `%ProgramData%\OpenAI\Codex\requirements.toml` |
| User configuration | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` |
| Managed defaults | `/etc/codex/managed_config.toml` or macOS MDM | `~/.codex/managed_config.toml` or approved device management |
| macOS MDM requirements | `com.openai.codex:requirements_toml_base64` | Not applicable |
| macOS MDM defaults | `com.openai.codex:config_toml_base64` | Not applicable |
| Platform sandbox | Native macOS sandbox | Required `elevated` Windows sandbox |

Cloud-managed enterprise requirements can also be assigned through the supported administration surface. Apply policies to a pilot group before assigning them to an entire fleet, and verify the highest-precedence effective policy on each platform.

## Choose the right approval model

| Approval model | Appropriate when | Security tradeoff |
| --- | --- | --- |
| `never` | Sandbox boundaries must not be widened by user approval. | Legitimate tasks requiring additional permission are rejected. Actions already allowed by the sandbox can still run. |
| `on-request` with `approvals_reviewer = "user"` | Human reviewers may approve individually justified exceptions. | A user can approve a request that executes outside the normal sandbox. It is not a non-overridable network-share prohibition. |
| Granular approvals | The installed client and enterprise policy support separately controlling sandbox, rule, skill, MCP, and permission prompts. | Support and managed-policy representation vary by client version and administration surface; validate the deployed combination before relying on it. |

For the strict blueprint, managed command rules use `decision = "forbidden"`. Do not use `decision = "prompt"` while also setting `approval_policy = "never"` and expect an interactive review: approval prompts are intentionally disabled.

If a supervised operating model requires `on-request`, update both the managed `allowed_approval_policies` setting and the client `approval_policy`. Treat user-approved exceptions as a deliberate security decision and preserve an operating-system control for resources that must never be accessed.

## Validate before rollout

The example directory includes a validator that requires Python `3.11` or later and uses only the standard library:

```bash
python examples/codex/regulated_industry_configuration/validate_blueprints.py
```

Expected output:

```text
PASS general: requirements.toml, config.toml
PASS macos: requirements.macos.toml, config.macos.toml
PASS windows: requirements.windows.toml, config.windows.toml
Validated 3 regulated-industry blueprint pairs for Codex 0.138.0 or later.
```

The validator checks TOML parsing, matching permission profiles, restricted filesystem roots, denied secret patterns, disabled command-network access, disabled approval escalation, MCP deny-by-default behavior, and the Windows elevated-sandbox requirement.

To also validate the client files and managed permission profiles against the exact deployed Codex release, save a trusted copy of that release's `config.schema.json` in the current directory and install `jsonschema`:

```bash
python -m pip install jsonschema
python examples/codex/regulated_industry_configuration/validate_blueprints.py \
  --schema ./config.schema.json
```

Run the regression tests:

```bash
python -m unittest discover \
  -s examples/codex/regulated_industry_configuration \
  -p 'test_*.py'
```

After deployment:

1. Start a new supported local Codex session.
2. Open `/debug-config` and confirm the expected requirements source, approval policy, and permission profile.
3. On Windows, confirm the elevated sandbox initialized without fallback.
4. Confirm the selected workspace is an approved local directory.
5. Review the active authentication, credential-storage, MCP, history, and telemetry settings.
6. If troubleshooting is needed, run `/feedback` in the current session and share the resulting feedback ID through an approved support process.

Avoid placing raw credentials, customer data, sensitive logs, or confidential source code in support messages or feedback descriptions.

## Understand the operational tradeoffs

The default policy intentionally disables networked development workflows, configurable MCP integrations, automatic approvals, repository publication from Codex, and persistent local history. It also withholds write access to temporary directories outside the selected workspace and can interfere with linked Git worktrees or tools that keep their caches elsewhere. That may be appropriate for an initial security review but too restrictive for a production engineering team.

Relax controls only after documenting the business need and enforcing the replacement boundary. Typical adjustments include approving a specific internal MCP server, permitting a reviewed network domain, enabling centrally governed telemetry, or adopting a supervised approval model for a lower-risk group.

Keep requirements and defaults synchronized, avoid unverified placeholders, review changes with security and platform owners, and rerun the validator for each platform-specific variant.

## References

- [Managed configuration and enterprise requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [Permission profiles and filesystem access](https://learn.chatgpt.com/docs/permissions)
- [Native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Managed execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
