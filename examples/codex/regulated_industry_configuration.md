# Configure Codex for regulated environments

Financial services, healthcare, public-sector, and other regulated organizations need more than a filesystem policy when they introduce an AI coding assistant. They need an operating model that covers identity, human oversight, permitted execution modes, network access, integrations, sensitive data, monitoring, change management, and device deployment.

This cookbook provides a general-purpose starting point for supported local Codex desktop, CLI, and IDE clients running version `0.138.0` or later. It includes one complete enterprise `requirements.toml`, one matching client `config.toml`, optional managed model governance for Codex `0.146.0` or later, deployment instructions for macOS and native Windows, and executable checks that keep the two files aligned.

The examples are technical deployment guidance, not a compliance certification, legal interpretation, contractual data-processing commitment, or substitute for an organization-specific risk assessment.

## Separate enterprise requirements from client defaults

Codex configuration operates across two layers:

| Layer | File | Purpose | Can the user override it? |
| --- | --- | --- | --- |
| Enterprise requirements | `requirements.toml` | Establish supported, non-overridable policy boundaries. | No, when delivered through a supported managed-requirements source. |
| Client configuration | `config.toml` | Establish client behavior, preferred defaults, and platform settings. | Yes, unless a matching requirement or external administrative control constrains the setting. |

Managed defaults delivered through `managed_config.toml` or macOS mobile device management (MDM) remain defaults. They do not automatically become enforced enterprise requirements.

Some controls also belong outside TOML. Identity-provider policies, single sign-on, endpoint restrictions, firewall rules, approved model access, contractual retention terms, and enterprise data-residency commitments must be enforced through the corresponding administrative, contractual, or operating-system control. Remote or cloud-hosted execution environments also require separately verified controls.

Managed permission-profile allowlists and managed default permission profiles require Codex `0.138.0` or later. Enforced managed model catalogs require Codex `0.146.0` or later. Verify the applicable minimum version across the entire device fleet before enabling either control.

## Define the regulated operating model

Use this control matrix when translating security and compliance requirements into Codex configuration:

| Governance area | Enterprise requirements | Client defaults and operational controls |
| --- | --- | --- |
| Identity and tenancy | Apply the correct managed policy to the intended enterprise users or groups. | Require enterprise ChatGPT sign-in, optionally bind a verified workspace ID, and enforce identity-provider controls. |
| Model governance | On Codex `0.146.0` or later, enforce an approved model catalog through managed requirements. | Select approved model and reasoning defaults; use server-side entitlements for actual model authorization. |
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

# Optional on Codex 0.146.0 or later: enforce an approved local model catalog.
# Deploy and protect the catalog on each device before enabling this requirement.
# model_catalog_json = "/etc/codex/approved-models.json"

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

# Optional approved-model defaults. Verify model access and install the catalog
# before enabling these settings; enforce the catalog through requirements.
# model = "gpt-5.6-luna"
# model_catalog_json = "/etc/codex/approved-models.json"

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

## Restrict visible models and reasoning options

Regulated organizations often want approved user groups to see only reviewed models and reasoning levels. From Codex `0.146.0`, administrators can enforce a local JSON model catalog through managed requirements and assign the policy to the appropriate enterprise users or groups.

These controls have different boundaries:

| Control | Configuration layer | Effect | Limitation |
| --- | --- | --- | --- |
| `model` and `model_reasoning_effort` | Client `config.toml` or managed defaults. | Select the preferred default model and reasoning effort. | Defaults do not independently prevent users from selecting another model. |
| `model_catalog_json` | Managed `requirements.toml` on Codex `0.146.0` or later. | Enforce the catalog that controls visible Codex models and reasoning options. | Does not establish server-side model authorization. |
| Workspace and product entitlements | Supported administrative and identity controls. | Govern actual model availability for the relevant account and product surface. | Must be reviewed separately for desktop, CLI, IDE, cloud, and API access. |

Set `model_catalog_json` as a top-level requirement before any TOML table headers. On macOS, a managed requirements file can use:

```toml
# requirements.toml - requires Codex 0.146.0 or later
model_catalog_json = "/etc/codex/approved-models.json"
```

On native Windows, use the equivalent protected local device path:

```toml
# requirements.toml - requires Codex 0.146.0 or later
model_catalog_json = 'C:\ProgramData\OpenAI\Codex\approved-models.json'
```

The path must reference a JSON file installed on the local device. An HTTPS URL does not distribute or load the catalog. Cloud-managed requirements can assign the path to an approved user or group, but the organization must still deploy the JSON file through its device-management process and prevent users from modifying it.

Add matching client defaults only after the approved model is available to the enterprise account:

```toml
# config.toml
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
model_catalog_json = "/etc/codex/approved-models.json"
```

On Windows, replace the catalog path with the single-quoted Windows path shown above. The `model_catalog_json` client setting exists in Codex `0.138.0`, but it is only an overridable client preference at that version. Do not describe it as enforced enterprise model policy before Codex `0.146.0`.

### Apply different model policies to enterprise groups

When different teams require different approved models, create a reviewed catalog and managed policy for each risk group. Assign the relevant cloud-managed requirements policy to the intended enterprise users or groups, distribute its matching protected catalog through device management, and verify that pilot users receive the expected model picker. Confirm that users outside the target group retain their intended policy and review source precedence when system, cloud-managed, or MDM requirements also apply.

Group assignment controls which catalog policy a Codex user receives. It does not replace workspace entitlements, backend authorization, or the organization's identity-provider access controls.

### Build an approved model catalog

A Codex model catalog contains complete model definitions, not just model names. Start with the raw catalog exposed by an authorized Codex client, preserve each approved model's full metadata, and remove models or reasoning options that the organization has not reviewed.

Save the following script as `build_approved_catalog.py`:

```python
import json
import subprocess
from pathlib import Path

APPROVED_MODELS = {"gpt-5.6-luna"}
APPROVED_REASONING_LEVELS = {"low", "medium"}

result = subprocess.run(
    ["codex", "debug", "models"],
    check=True,
    capture_output=True,
    text=True,
)
catalog = json.loads(result.stdout)
catalog["models"] = [
    model for model in catalog["models"] if model["slug"] in APPROVED_MODELS
]

if not catalog["models"]:
    raise SystemExit("None of the approved models are available to this account.")

for model in catalog["models"]:
    model["supported_reasoning_levels"] = [
        level
        for level in model["supported_reasoning_levels"]
        if level["effort"] in APPROVED_REASONING_LEVELS
    ]
    if not model["supported_reasoning_levels"]:
        raise SystemExit(f"No approved reasoning levels remain for {model['slug']}.")

    allowed_efforts = {
        level["effort"] for level in model["supported_reasoning_levels"]
    }
    if model["default_reasoning_level"] not in allowed_efforts:
        model["default_reasoning_level"] = model["supported_reasoning_levels"][0][
            "effort"
        ]

output_path = Path("approved-models.json")
output_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
print(f"Created {output_path} with {len(catalog['models'])} approved model(s).")
```

Run `python build_approved_catalog.py` from an authorized account before deploying the managed requirement. Review the resulting JSON, distribute it to the protected path on each target device, and restart Codex after updating it. The catalog is loaded at startup; clients do not automatically reload catalog changes.

The example model is illustrative and must be verified against the organization's approved model list, current entitlement, and deployed client version. Maintain the catalog as a versioned enterprise artifact, refresh it when approved models change, and pilot the policy with the intended user group before wider rollout.

An enforced catalog governs the Codex catalog and model picker. It does not establish a backend authorization boundary or prevent a different product surface or API credential from reaching a model that the backend still authorizes. When a model must be inaccessible rather than hidden from normal selection, require the corresponding server-side administrative or entitlement control and verify its effective behavior.

## Review the major governance decisions

### Identity, workspace, and model access

Bind deployment to the correct enterprise tenant through the organization's identity provider, provisioning process, and approved ChatGPT workspace. If workspace binding is required, configure `forced_chatgpt_workspace_id` with the verified production identifier instead of copying a placeholder value.

Keep `model_reasoning_effort` aligned with latency, cost, and workload needs. For managed catalog restrictions, upgrade all targeted clients to Codex `0.146.0` or later and use the supported `model_catalog_json` requirement. Actual model authorization, provider approval, account entitlements, and contractual data-processing conditions still require their own supported administrative controls. Do not add an invented `allowed_models` requirement to the Codex `0.138.0` baseline.

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

After enabling an approved model catalog on a supported client, validate the deployed files, client version, selected model, permitted reasoning levels, and catalog contents together:

```bash
python examples/codex/regulated_industry_configuration/validate_blueprints.py \
  --codex-version 0.146.0 \
  --requirements /etc/codex/requirements.toml \
  --config "$HOME/.codex/config.toml" \
  --model-catalog /etc/codex/approved-models.json
```

For Windows, use `--platform windows` and replace the three file paths with the corresponding `%ProgramData%` and `%USERPROFILE%` deployment locations.

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
4. If a managed model catalog is enabled, verify the client version, active policy source, approved models, reasoning levels, protected catalog path, and backend model entitlements.
5. Check web-search mode, command networking, analytics, local history, and approved telemetry settings.
6. Validate that sensitive development actions prompt for review and protected production actions are forbidden.
7. On Windows, confirm the elevated sandbox initializes without fallback.
8. If investigation is required, run `/feedback` in the active session and share the resulting feedback ID through the approved support process.

Do not include raw credentials, customer data, confidential source code, or other sensitive material in support messages.

## Adapt the baseline to the organization

Use one managed baseline as the starting point, then create reviewed variations for distinct risk groups. A software engineering group might permit cached search and approved repository integrations, while a production-support group could use read-only permissions and a no-exception approval policy.

Review each change across the full operating model: identity, human oversight, execution, network access, integrations, sensitive data, auditability, and endpoint controls. Keep the two shared files synchronized, avoid unverified identifiers, and validate any Windows-only settings added during deployment.

## References

- [Managed configuration and enterprise requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [Workspace model availability and administrative controls](https://learn.chatgpt.com/docs/enterprise/workspace-model-availability)
- [Permission profiles and execution boundaries](https://learn.chatgpt.com/docs/permissions)
- [Native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Managed execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
