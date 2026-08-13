# Configure Codex for regulated environments

Financial services, healthcare, public-sector, and other regulated organizations need more than a filesystem policy when they introduce an AI coding assistant. They need an operating model that covers identity, human oversight, permitted execution modes, network access, integrations, sensitive data, monitoring, change management, and device deployment.

This cookbook provides a general-purpose starting point for supported local Codex desktop, CLI, and IDE clients running version `0.138.0` or later. It includes one complete enterprise `requirements.toml`, one matching client `config.toml`, deployment instructions for macOS and native Windows, and executable checks that keep the two files aligned.

The examples are technical deployment guidance, not a compliance certification, legal interpretation, contractual data-processing commitment, or substitute for an organization-specific risk assessment.

## Separate enterprise requirements from client defaults

Codex configuration operates across two layers:

| Layer | File | Purpose | Can the user override it? |
| --- | --- | --- | --- |
| Enterprise requirements | `requirements.toml` | Establish supported, non-overridable policy boundaries. | No, when delivered through a supported managed-requirements source. |
| Client configuration | `config.toml` | Establish client behavior, preferred defaults, and platform settings. | Yes, unless a matching requirement or external administrative control constrains the setting. |

Managed defaults delivered through `managed_config.toml` or macOS mobile device management (MDM) remain defaults. They do not automatically become enforced enterprise requirements.

Some controls also belong outside TOML. Identity-provider policies, single sign-on, endpoint restrictions, firewall rules, approved model access, contractual retention terms, and enterprise data-residency commitments must be enforced through the corresponding administrative, contractual, or operating-system control. Remote or cloud-hosted execution environments also require separately verified controls.

Managed permission-profile allowlists and managed default permission profiles require Codex `0.138.0` or later. Earlier clients do not enforce those controls, so verify the minimum version across the entire device fleet before rollout.

## Define the regulated operating model

Use this control matrix when translating security and compliance requirements into Codex configuration:

| Governance area | Enterprise requirements | Client defaults and operational controls |
| --- | --- | --- |
| Identity and tenancy | Apply the correct managed policy to the intended enterprise users or groups. | Require enterprise ChatGPT sign-in, optionally bind a verified workspace ID, and enforce identity-provider controls. |
| Human oversight | Allow only approved approval policies and human reviewers. | Default to human-reviewed `on-request` execution. |
| Execution boundaries | Allow read-only and workspace-write modes; exclude full access. | Select an approved managed permission profile. |
| Network and web search | Allow only reviewed web-search modes and restrict command-network access. | Default to cached search and disable command networking. |
| Apps, MCP, and plugins | Deny unapproved MCP identities and disable high-risk managed features. | Disable apps by default and enable integrations only after review. |
| Credentials and secrets | Protect sensitive files through the approved permission profile. | Store credentials in the operating-system keyring and restrict inherited shell variables. |
| Data handling | Enforce only supported product requirements; do not invent residency values. | Minimize local history, disable analytics where appropriate, and suppress prompt logging. |
| Monitoring and support | Review managed hooks and change-control rules. | Configure approved OpenTelemetry settings and retain the ability to submit `/feedback`. |
| Production safety | Require approval for sensitive development actions and forbid protected production changes. | Route deployment, infrastructure, and merge actions through approved workflows. |
| Device security | Add the elevated Windows sandbox requirement where native Windows is used. | Add the matching Windows client settings and verify effective device policy. |

The baseline below is supervised, not maximally restrictive. It supports normal engineering work while reserving sensitive actions for human review. Organizations that cannot allow user-approved exceptions should adopt the stricter approval model described later.

## Create the enterprise requirements file

The complete portable managed policy is available as [requirements.toml](regulated_industry_configuration/requirements.toml):

```toml
# Cross-platform regulated-enterprise requirements for Codex 0.138.0 or later.
# Deploy through enterprise-managed configuration or the system policy path.
# These requirements establish governance boundaries, not user defaults.

allowed_approval_policies = ["on-request", "untrusted"]
allowed_approvals_reviewers = ["user"]
allowed_sandbox_modes = ["read-only", "workspace-write"]
allowed_web_search_modes = ["disabled", "cached"]
default_permissions = "regulated_workspace"
allow_managed_hooks_only = true
allow_appshots = false

# An explicit empty allowlist disables configurable MCP servers. Replace it
# only after approving an exact server name and its verified identity.
mcp_servers = {}

# Permit inspection-only work and the approved engineering profile, but not
# unrestricted full access or unmanaged custom profiles.
[allowed_permission_profiles]
":read-only" = true
regulated_workspace = true

# Extend the standard workspace profile for normal engineering compatibility.
# Organizations that require narrower reads should define explicit roots instead.
[permissions.regulated_workspace]
description = "Use the standard workspace sandbox with human oversight, protected secrets, and restricted command networking."
extends = ":workspace"

[permissions.regulated_workspace.filesystem]
glob_scan_max_depth = 6

[permissions.regulated_workspace.filesystem.":workspace_roots"]
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

[features]
browser_use = false
browser_use_external = false
computer_use = false
enable_mcp_apps = false
guardian_approval = false
in_app_browser = false
memories = false
memory_tool = false
remote_control = false
skill_mcp_dependency_install = false

# Require human review for sensitive development actions. Block production and
# infrastructure changes that belong in an approved deployment workflow.
[rules]
prefix_rules = [
  { pattern = [{ any_of = ["rm", "rmdir"] }], decision = "prompt", justification = "A human must review destructive filesystem operations." },
  { pattern = [{ any_of = ["curl", "wget"] }], decision = "prompt", justification = "A human must review attempted network access or data transfer." },
  { pattern = [{ token = "git" }, { any_of = ["commit", "push"] }], decision = "prompt", justification = "A human must approve repository commits and publication." },
  { pattern = [{ token = "kubectl" }, { any_of = ["apply", "delete", "patch", "exec", "edit"] }], decision = "forbidden", justification = "Production changes require approved deployment pipelines." },
  { pattern = [{ token = "terraform" }, { any_of = ["apply", "destroy"] }], decision = "forbidden", justification = "Infrastructure changes require approved change management." },
  { pattern = [{ token = "gh" }, { token = "pr" }, { token = "merge" }], decision = "forbidden", justification = "Pull-request merges remain human-controlled actions outside Codex." },
]
```

This file establishes the organization-wide guardrails:

- Human reviewers approve sensitive operations; automated approval review is not permitted.
- Full-access execution modes and unapproved permission profiles are unavailable.
- Live web search is unavailable, but the organization can choose cached search or disable search entirely.
- Configurable MCP servers are blocked until an exact approved server identity is added.
- Browser control, computer use, persistent memory, remote control, unmanaged hooks, and other high-risk features are restricted.
- Repository publication and destructive operations require review, while protected infrastructure and production actions are forbidden.

An explicit empty `mcp_servers = {}` allowlist blocks MCP servers. Omitting `mcp_servers` does not create the same restriction. Add an integration only after verifying its exact server identity, data access, ownership, and approval model.

## Create the matching client configuration

The complete portable client configuration is available as [config.toml](regulated_industry_configuration/config.toml):

```toml
#:schema https://developers.openai.com/codex/config-schema.json
# Cross-platform device or user defaults for Codex 0.138.0 or later.
# Pair this file with the corresponding enforced requirements.toml.

approval_policy = "on-request"
approvals_reviewer = "user"
default_permissions = "regulated_workspace"
web_search = "cached"
allow_login_shell = false
model_reasoning_effort = "medium"

forced_login_method = "chatgpt"
cli_auth_credentials_store = "keyring"
mcp_oauth_credentials_store = "keyring"

[apps._default]
enabled = false
destructive_enabled = false
open_world_enabled = false

[analytics]
enabled = false

[feedback]
enabled = true

[history]
persistence = "none"

[shell_environment_policy]
inherit = "core"
ignore_default_excludes = false
exclude = ["*PASSWORD*", "*CREDENTIAL*", "*PRIVATE*"]

[sandbox_workspace_write]
network_access = false

[otel]
environment = "regulated-production"
log_user_prompt = false
```

Use the client settings to establish a consistent starting experience across devices:

- `forced_login_method = "chatgpt"` selects the enterprise ChatGPT authentication flow.
- Add `forced_chatgpt_workspace_id` only after obtaining and verifying the organization's actual workspace identifier.
- Keyring-backed credential storage avoids silently falling back to a local credentials file.
- Cached web search avoids live search, but search queries must still be permitted by the organization's data-handling policy.
- Disabled analytics and local history reduce optional local or product telemetry, while approved OpenTelemetry settings can support enterprise observability.
- `log_user_prompt = false` avoids including raw prompts in the configured OpenTelemetry stream.
- Keeping feedback enabled supports current-session troubleshooting without requiring persistent local history.

Identity restrictions, credential-storage preferences, analytics, local history, telemetry, login-shell behavior, and Windows private-desktop settings remain client defaults unless a supported managed requirement or external administrative control enforces them.

## Review the major governance decisions

### Identity, workspace, and model access

Bind deployment to the correct enterprise tenant through the organization's identity provider, provisioning process, and approved ChatGPT workspace. If workspace binding is required, configure `forced_chatgpt_workspace_id` with the verified production identifier instead of copying a placeholder value.

Keep `model_reasoning_effort` aligned with latency, cost, and workload needs. Model availability, provider approval, account entitlements, and contractual data-processing conditions require their own supported administrative controls. Do not add an invented `allowed_models` requirement to this Codex `0.138.0` baseline.

### Approval policies and separation of duties

| Operating model | Managed approval policy | Result |
| --- | --- | --- |
| Supervised engineering | `on-request` or `untrusted`, with reviewer `user`. | Sensitive actions can be approved by a human; `prompt` execution rules remain usable. |
| Non-overridable sandbox boundary | `never`, with matching client configuration. | Actions requiring additional approval are rejected instead of presented to a user. |
| Fine-grained control | A supported granular approval configuration. | Some prompt categories can remain available while other categories are rejected; verify support across the deployed client and management surface. |

`on-request` can allow a user to approve execution outside the normal sandbox. It is appropriate only when user-approved exceptions are part of the operating model. When that is unacceptable, set `allowed_approval_policies = ["never"]`, set `approval_policy = "never"`, and replace `prompt` command rules with `forbidden` rules where required.

The supplied validator checks the supervised reference baseline. If you intentionally create a stricter no-exception variant, update its approval-policy and command-rule assertions before using it to validate that separate profile.

### Network access, search, and integrations

The example disables network access for sandboxed commands and live web search. It does not disable the Codex client's authenticated model-service connection, enterprise configuration, or account sign-in. Govern those connections through approved identity, proxy, and egress policies.

If engineering teams need package registries, source-control services, or internal APIs, introduce a reviewed network allowlist and test the installed client's managed-network controls. Approve MCP servers and apps individually based on verified ownership, reachable systems, data exposure, and write permissions.

### Data retention, telemetry, and residency

`history.persistence = "none"` reduces local session-history retention. It can also make incident reconstruction harder, so pair the setting with an approved enterprise audit or observability process when your retention policy requires one.

Configure an OpenTelemetry exporter only after the destination, authentication, data classification, retention, and access controls have been approved. The example intentionally omits collector URLs, bearer tokens, workspace identifiers, and other organization-specific values.

In the exact Codex `0.138.0` requirements schema, `enforce_residency` accepts `"us"`; `"eu"` is not an accepted value. Do not assume a TOML setting establishes EU residency or satisfies a contractual residency commitment. Validate supported residency controls separately with the applicable enterprise administrators and legal or security owners.

### Filesystem access as one part of the policy

The example extends the built-in `:workspace` profile for compatibility with ordinary development tools. That profile can inherit broader filesystem reads than a dedicated read-isolation policy. When an organization must prevent access to network shares or other directories, define explicit readable roots with a stricter custom profile and enforce the same boundary through operating-system and endpoint controls.

A selected workspace is trusted by its workspace profile. If a prohibited network share is selected as the workspace, the profile includes that share by definition. Prevent prohibited workspace selection through identity, endpoint, operating-system, or file-share policy.

On Windows, wildcard deny rules are expanded against existing files and use the configured scan depth. The explicit `.env` and `.env.local` entries protect known paths, but deeper files or newly created wildcard-only matches require additional review and operating-system controls.

Command-prefix rules provide an additional review boundary, but they do not semantically inspect every possible shell script. Do not treat those rules as a replacement for sandbox, endpoint, or identity controls.

## Deploy on macOS

Deploy the same portable [requirements.toml](regulated_industry_configuration/requirements.toml) and [config.toml](regulated_industry_configuration/config.toml) shown above. No additional macOS-specific TOML files are required.

### Install managed requirements as a system file

From the cookbook repository root:

```bash
BLUEPRINT_DIR="examples/codex/regulated_industry_configuration"

sudo install -d -m 0755 /etc/codex
sudo install -m 0644 \
  "$BLUEPRINT_DIR/requirements.toml" \
  /etc/codex/requirements.toml

mkdir -p "$HOME/.codex"
install -m 0600 \
  "$BLUEPRINT_DIR/config.toml" \
  "$HOME/.codex/config.toml"
```

For centrally managed defaults, deploy the client configuration to `/etc/codex/managed_config.toml` through the organization's device-management workflow. Keep enforceable controls in the requirements layer.

### Distribute policy through macOS MDM

The managed-preferences domain is `com.openai.codex`. Use `requirements_toml_base64` for enterprise requirements and `config_toml_base64` for managed defaults.

Create the requirements payload without line wrapping:

```bash
base64 -i \
  examples/codex/regulated_industry_configuration/requirements.toml \
  | tr -d '\n'
```

Create the defaults payload separately:

```bash
base64 -i \
  examples/codex/regulated_industry_configuration/config.toml \
  | tr -d '\n'
```

Install each value under the corresponding managed-preferences key. Existing MDM policies can take precedence over other managed sources, so inspect the effective configuration before expanding deployment.

## Deploy on native Windows

Start with the same portable [requirements.toml](regulated_industry_configuration/requirements.toml) and [config.toml](regulated_industry_configuration/config.toml). For Windows deployments that require the stronger native sandbox, add the following section to the deployed `requirements.toml`:

```toml
[windows]
allowed_sandbox_implementations = ["elevated"]
```

Add the matching section to the deployed `config.toml` to select that implementation and keep private-desktop isolation enabled:

```toml
[windows]
sandbox = "elevated"
sandbox_private_desktop = true
```

`elevated` describes the Windows sandbox implementation and setup; it does not grant the agent unrestricted administrator privileges. Administrators may need to approve endpoint prerequisites, local sandbox-user creation, or firewall configuration.

Keep these Windows-only additions in the Windows deployment workflow. The shared reference files remain platform-neutral and can also be deployed unchanged on macOS.

From an approved administrative PowerShell session at the cookbook repository root:

```powershell
$blueprintDirectory = Join-Path `
    (Get-Location) `
    "examples\codex\regulated_industry_configuration"

$managedDirectory = Join-Path $env:ProgramData "OpenAI\Codex"
$userDirectory = Join-Path $env:USERPROFILE ".codex"
$deployedRequirements = Join-Path $managedDirectory "requirements.toml"
$deployedConfig = Join-Path $userDirectory "config.toml"

New-Item -ItemType Directory -Path $managedDirectory -Force
New-Item -ItemType Directory -Path $userDirectory -Force

Copy-Item `
    (Join-Path $blueprintDirectory "requirements.toml") `
    $deployedRequirements

Copy-Item `
    (Join-Path $blueprintDirectory "config.toml") `
    $deployedConfig

Add-Content -Path $deployedRequirements -Value @'

[windows]
allowed_sandbox_implementations = ["elevated"]
'@

Add-Content -Path $deployedConfig -Value @'

[windows]
sandbox = "elevated"
sandbox_private_desktop = true
'@
```

The system requirements path is `%ProgramData%\OpenAI\Codex\requirements.toml`; the user configuration path is `%USERPROFILE%\.codex\config.toml`. Prefer the organization's standard endpoint-management tooling for production rollout.

At Codex `0.138.0`, `allowed_sandbox_implementations` belongs in Windows managed requirements, while `sandbox_private_desktop` belongs in client configuration. Do not place private-desktop settings inside `[windows]` in `requirements.toml` for that version.

## Compare deployment approaches

| Configuration source | macOS | Native Windows |
| --- | --- | --- |
| Enforced system requirements | `/etc/codex/requirements.toml` | `%ProgramData%\OpenAI\Codex\requirements.toml` |
| User configuration | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` |
| Managed defaults | `/etc/codex/managed_config.toml` or macOS MDM | `~/.codex/managed_config.toml` or approved device management |
| MDM requirements | `com.openai.codex:requirements_toml_base64` | Not applicable |
| MDM defaults | `com.openai.codex:config_toml_base64` | Not applicable |
| Platform sandbox | Native macOS sandbox | Required elevated Windows sandbox |

Where supported, enterprise administrators can also assign cloud-managed requirements to specific user groups. Start with a pilot group, verify the effective policy for pilot and non-pilot users, and resolve precedence between cloud-managed, system, and MDM sources before broader deployment.

## Validate the examples and rollout

The example directory includes a validator that requires Python `3.11` or later and uses only the standard library:

```bash
python examples/codex/regulated_industry_configuration/validate_blueprints.py
```

Expected output:

```text
PASS general: requirements.toml, config.toml
Validated 1 regulated-industry blueprint pair for Codex 0.138.0 or later.
```

The validator checks enterprise approval boundaries, allowed operating modes, web-search governance, permission profiles, MCP restrictions, managed features, change-control rules, identity and credential defaults, analytics, history, and observability.

After adding the Windows-specific sections to the two deployed files, validate their effective content from PowerShell:

```powershell
python examples/codex/regulated_industry_configuration/validate_blueprints.py `
  --platform windows `
  --requirements "$env:ProgramData\OpenAI\Codex\requirements.toml" `
  --config "$env:USERPROFILE\.codex\config.toml"
```

To validate client configuration and managed permission profiles against the exact deployed release, save a trusted copy of its `config.schema.json` in the current directory:

```bash
python -m pip install jsonschema
python examples/codex/regulated_industry_configuration/validate_blueprints.py \
  --schema ./config.schema.json
```

Run the regression suite:

```bash
python -m unittest discover \
  -s examples/codex/regulated_industry_configuration \
  -p 'test_*.py'
```

After deploying a pilot:

1. Confirm every local client meets the minimum supported version.
2. Open `/debug-config` and verify the active requirements source, approval settings, and selected permission profile.
3. Confirm the correct enterprise authentication flow, workspace, credential store, and permitted integrations.
4. Check web-search mode, command networking, analytics, local history, and approved telemetry settings.
5. Validate that sensitive development actions prompt for review and protected production actions are forbidden.
6. On Windows, confirm the elevated sandbox initializes without fallback.
7. If investigation is required, run `/feedback` in the active session and share the resulting feedback ID through the approved support process.

Do not include raw credentials, customer data, confidential source code, or other sensitive material in support messages.

## Adapt the baseline to the organization

Use one managed baseline as the starting point, then create reviewed variations for distinct risk groups. A software engineering group might permit cached search and approved repository integrations, while a production-support group could use read-only permissions and a no-exception approval policy.

Review each change across the full operating model: identity, human oversight, execution, network access, integrations, sensitive data, auditability, and endpoint controls. Keep the two shared files synchronized, avoid unverified identifiers, and validate any Windows-only settings added during deployment.

## References

- [Managed configuration and enterprise requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [Permission profiles and execution boundaries](https://learn.chatgpt.com/docs/permissions)
- [Native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Managed execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
