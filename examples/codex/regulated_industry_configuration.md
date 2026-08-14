# Configure Codex for regulated environments

Financial services, healthcare, public-sector, and other regulated organizations need more than a filesystem policy when they introduce an AI coding assistant. They need an operating model that covers identity, human oversight, permitted execution modes, network access, integrations, sensitive data, monitoring, change management, and device deployment.

This cookbook provides a general-purpose starting point for the latest supported local Codex desktop, CLI, and IDE clients. It includes one complete enterprise `requirements.toml`, one matching client `config.toml`, managed model and identity governance, deployment instructions for macOS and native Windows, and executable checks that keep the two files aligned.

The examples are technical deployment guidance, not a compliance certification, legal interpretation, contractual data-processing commitment, or substitute for an organization-specific risk assessment.

## Separate enterprise requirements from client defaults

Codex configuration operates across two layers:

| Layer | File | Purpose | Can the user override it? |
| --- | --- | --- | --- |
| Enterprise requirements | `requirements.toml` | Establish supported, non-overridable policy boundaries. | No, when delivered through a supported managed-requirements source. |
| Client configuration | `config.toml` | Establish client behavior, preferred defaults, and platform settings. | Yes, unless a matching requirement or external administrative control constrains the setting. |

Managed defaults delivered through `managed_config.toml` or macOS mobile device management (MDM) remain defaults. They do not automatically become enforced enterprise requirements.

Some controls also belong outside TOML. Identity-provider policies, single sign-on, endpoint restrictions, firewall rules, approved model access, contractual retention terms, and enterprise data-residency commitments must be enforced through the corresponding administrative, contractual, or operating-system control. Remote or cloud-hosted execution environments also require separately verified controls.

Always keep every supported Codex surface on the latest available release through the organization's approved software-distribution and change-management process. Validate managed settings against the current configuration reference and the schema bundled with the installed release before deployment. Outdated clients may not support or enforce current enterprise requirements consistently.

Where the approved deployment process uses npm, install the current release without pinning a specific Codex release number:

```bash
npm install -g @openai/codex@latest
```

Update managed desktop and IDE installations through the organization's approved application-management process. Do not ask users to bypass endpoint, administrator, or package-registry controls to update their clients.

Permission profiles replace the older `sandbox_mode` and `[sandbox_workspace_write]` configuration. When a deployment uses managed permission profiles, do not mix those older client settings into `config.toml`; define filesystem and command-network boundaries inside the selected permission profile instead.

## Define the regulated operating model

Use this control matrix when translating security and compliance requirements into Codex configuration:

| Governance area | Enterprise requirements | Client defaults and operational controls |
| --- | --- | --- |
| Identity and tenancy | Require enterprise ChatGPT sign-in and, when appropriate, restrict users to verified enterprise workspace IDs. | Apply the correct group policy, configure matching login defaults, and enforce identity-provider controls. |
| Model governance | Enforce an approved model catalog through managed requirements when the organization restricts model selection. | Select approved model and reasoning defaults; use server-side entitlements for actual model authorization. |
| Human oversight | Allow only approved approval policies and human reviewers. | Default to human-reviewed `on-request` execution. |
| Execution boundaries | Allow only approved inspection and workspace permission profiles; exclude full access. | Select the reviewed managed permission profile without mixing legacy sandbox settings. |
| Network and web search | Allow only reviewed web-search modes and restrict command-network access. | Default to cached search and disable command networking. |
| Apps, MCP, and plugins | Deny unapproved standalone and plugin-bundled MCP identities and disable high-risk managed features. | Disable apps by default and enable plugins or connectors only after review. |
| Credentials and secrets | Protect sensitive files through both global managed read denials and the approved permission profile. | Store credentials in the operating-system keyring and restrict inherited shell variables. |
| Data handling | Enforce only supported product requirements; do not invent residency values. | Minimize local history, disable analytics where appropriate, and suppress prompt logging. |
| Monitoring and support | Review managed hooks and change-control rules. | Configure approved OpenTelemetry settings and retain the ability to submit `/feedback`. |
| Production safety | Require approval for sensitive development actions and forbid protected production changes. | Route deployment, infrastructure, and merge actions through approved workflows. |
| Device security | Prefer the elevated Windows sandbox and enforce private-desktop isolation. | Document any approved unelevated exception, compensating controls, and remediation plan. |

The baseline below is supervised, not maximally restrictive. It supports normal engineering work while reserving sensitive actions for human review. Organizations that cannot allow user-approved exceptions should adopt the stricter approval model described later.

## Create the enterprise requirements file

The complete portable managed policy is available as [requirements.toml](regulated_industry_configuration/requirements.toml):

```toml
# Cross-platform regulated-enterprise requirements for the latest Codex release.
# Deploy through enterprise-managed configuration or the system policy path.
# These requirements establish governance boundaries, not user defaults.

allowed_login_methods = ["chatgpt"]
allowed_approval_policies = ["on-request", "untrusted"]
allowed_approvals_reviewers = ["user"]
allowed_web_search_modes = ["disabled", "cached"]
default_permissions = "regulated_workspace"
allow_login_shell = false
allow_managed_hooks_only = true
allow_appshots = false
allow_remote_control = false

# Optionally enforce an approved model catalog installed on each managed device.
# model_catalog_json = "/etc/codex/approved-models.json"

# Explicit empty allowlists block standalone and plugin-bundled MCP servers.
# Add only approved, verified server and plugin identities.
mcp_servers = {}
plugins = {}

# Pin approved enterprise workspace IDs only after independently verifying them.
# Configure allowed_chatgpt_workspaces through the managed deployment workflow.

[allowed_permission_profiles]
":read-only" = true
regulated_read_only = true
regulated_workspace = true

[permissions.regulated_read_only]
description = "Inspect approved files without modifying the workspace or using command networking."
extends = ":read-only"

[permissions.regulated_read_only.network]
enabled = false

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

# Protect sensitive credentials across approved profiles, not only inside roots.
# Native Windows shell reads also require operating-system and endpoint controls.
[permissions.filesystem]
deny_read = [
  "~/.ssh/id_rsa",
  "~/.ssh/id_ed25519",
  "~/.aws/credentials",
  "~/.azure",
  "~/.config/gcloud",
  "~/.kube/config",
  "~/.docker/config.json",
  "~/.npmrc",
  "~/.pypirc",
  "~/.netrc",
  "/**/.env",
  "/**/*.env",
  "/**/*.pem",
  "/**/*.key",
  "/**/*.p12",
  "/**/*.pfx",
]

[features]
browser_use = false
browser_use_external = false
computer_use = false
enable_mcp_apps = false
guardian_approval = false
in_app_browser = false
memories = false
memory_tool = false
plugin_sharing = false
remote_control = false
remote_plugin = false
skill_mcp_dependency_install = false

# Prompt for reviewable engineering actions and forbid high-risk operations.
[rules]
prefix_rules = [
  { pattern = [{ token = "rm" }, { any_of = ["-rf", "-fr", "-Rf", "-fR"] }], decision = "forbidden", justification = "Forced recursive deletion is not allowed." },
  { pattern = [{ token = "Remove-Item" }, { token = "-Recurse" }, { token = "-Force" }], decision = "forbidden", justification = "Forced recursive deletion is not allowed." },
  { pattern = [{ token = "Remove-Item" }, { token = "-Force" }, { token = "-Recurse" }], decision = "forbidden", justification = "Forced recursive deletion is not allowed." },
  { pattern = [{ any_of = ["rm", "rmdir", "del", "Remove-Item"] }], decision = "prompt", justification = "A human must review destructive filesystem operations." },
  { pattern = [{ token = "git" }, { token = "reset" }, { token = "--hard" }], decision = "forbidden", justification = "A hard reset can discard uncommitted work." },
  { pattern = [{ token = "git" }, { any_of = ["commit", "push", "clean", "rebase", "checkout", "switch"] }], decision = "prompt", justification = "A human must approve repository mutations and publication." },
  { pattern = [{ any_of = ["curl", "wget", "Invoke-WebRequest", "Invoke-RestMethod"] }], decision = "prompt", justification = "A human must review attempted data transfer." },
  { pattern = [{ any_of = ["npm", "pnpm", "yarn", "pip", "pip3", "uv"] }, { any_of = ["install", "add"] }], decision = "prompt", justification = "Dependency changes require approved package sources and human review." },
  { pattern = [{ any_of = ["docker", "podman"] }, { any_of = ["run", "pull", "build", "push"] }], decision = "prompt", justification = "Container execution and registry changes require human review." },
  { pattern = [{ any_of = ["ngrok", "localtunnel", "devtunnel"] }], decision = "forbidden", justification = "Public tunneling is not allowed; use an approved internal environment." },
  { pattern = [{ token = "cloudflared" }, { token = "tunnel" }], decision = "forbidden", justification = "Public tunneling is not allowed; use an approved internal environment." },
  { pattern = [{ token = "code" }, { token = "tunnel" }], decision = "forbidden", justification = "Editor tunnels are not allowed without an approved exception." },
  { pattern = [{ token = "ssh" }, { any_of = ["-R", "-L", "-D"] }], decision = "forbidden", justification = "SSH port forwarding and tunnels require an approved external workflow." },
  { pattern = [{ any_of = ["sudo", "su", "runas", "pkexec"] }], decision = "forbidden", justification = "Privilege escalation is not allowed from agent-managed sessions." },
  { pattern = [{ any_of = ["mimikatz", "procdump", "procdump.exe"] }], decision = "forbidden", justification = "Credential extraction and process-memory dumping are not allowed." },
  { pattern = [{ any_of = ["reg", "reg.exe"] }, { any_of = ["add", "delete", "import"] }], decision = "forbidden", justification = "Windows registry changes require approved endpoint-management workflows." },
  { pattern = [{ any_of = ["sc", "sc.exe"] }, { any_of = ["create", "config", "delete"] }], decision = "forbidden", justification = "Windows service changes require approved endpoint-management workflows." },
  { pattern = [{ token = "kubectl" }, { any_of = ["apply", "delete", "patch", "exec", "edit", "port-forward"] }], decision = "forbidden", justification = "Production changes and service exposure require approved deployment pipelines." },
  { pattern = [{ token = "terraform" }, { any_of = ["apply", "destroy"] }], decision = "forbidden", justification = "Infrastructure changes require approved change management." },
  { pattern = [{ token = "gh" }, { token = "pr" }, { token = "merge" }], decision = "forbidden", justification = "Pull-request merges remain human-controlled actions outside Codex." },
]
```

This file establishes the organization-wide guardrails:

- Human reviewers approve sensitive operations; automated approval review is not permitted.
- Enterprise ChatGPT sign-in is enforced, and verified workspace allowlists can be added during managed deployment.
- Full-access execution modes and unapproved permission profiles are unavailable.
- Live web search is unavailable, but the organization can choose cached search or disable search entirely.
- Standalone and plugin-bundled MCP servers are blocked until exact approved identities are added.
- Global read restrictions protect common SSH, cloud, package-manager, container, and certificate credentials across approved profiles.
- Browser control, computer use, persistent memory, remote plugins, plugin sharing, device remote control, unmanaged hooks, and other high-risk features are restricted.
- Repository publication, dependency changes, container operations, and reviewable file deletion require human approval.
- Public tunnels, privilege escalation, credential extraction, destructive repository changes, and protected infrastructure actions are forbidden.

An explicit empty `mcp_servers = {}` allowlist blocks standalone MCP servers. An explicit empty `plugins = {}` allowlist blocks unapproved plugin-bundled MCP servers. Omitting either table does not create the same restriction. Add an integration only after verifying its exact server identity, data access, ownership, and approval model. The `plugin_sharing` restriction specifically applies to supported cloud-managed requirements, so verify its behavior for the organization's chosen management surface.

## Create the matching client configuration

The complete portable client configuration is available as [config.toml](regulated_industry_configuration/config.toml):

```toml
#:schema https://developers.openai.com/codex/config-schema.json
# Cross-platform device or user defaults for the latest Codex release.
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

[otel]
environment = "regulated-production"
log_user_prompt = false
```

Use the client settings to establish a consistent starting experience across devices:

- `forced_login_method = "chatgpt"` selects the enterprise ChatGPT authentication flow.
- Add `forced_chatgpt_workspace_id` only after obtaining and verifying the organization's actual workspace identifier, and keep it aligned with any managed workspace allowlist.
- Keyring-backed credential storage avoids silently falling back to a local credentials file.
- Cached web search avoids live search, but search queries must still be permitted by the organization's data-handling policy.
- Disabled analytics and local history reduce optional local or product telemetry, while approved OpenTelemetry settings can support enterprise observability.
- `log_user_prompt = false` avoids including raw prompts in the configured OpenTelemetry stream.
- Keeping feedback enabled supports current-session troubleshooting without requiring persistent local history.

Credential-storage preferences, analytics, local history, telemetry, and other client settings remain defaults unless a supported managed requirement or external administrative control enforces them. The reference policy separately enforces enterprise login methods, login-shell restrictions, and device remote-control restrictions.

## Restrict visible models and reasoning options

Regulated organizations often want approved user groups to see only reviewed models and reasoning levels. Administrators can enforce a local JSON model catalog through managed requirements and assign the policy to the appropriate enterprise users or groups. Keep clients updated so the managed catalog and group-targeted policy remain supported.

These controls have different boundaries:

| Control | Configuration layer | Effect | Limitation |
| --- | --- | --- | --- |
| `model` and `model_reasoning_effort` | Client `config.toml` or managed defaults. | Select the preferred default model and reasoning effort. | Defaults do not independently prevent users from selecting another model. |
| `model_catalog_json` | Managed `requirements.toml`. | Enforce the catalog that controls visible Codex models and reasoning options. | Does not establish server-side model authorization. |
| Workspace and product entitlements | Supported administrative and identity controls. | Govern actual model availability for the relevant account and product surface. | Must be reviewed separately for desktop, CLI, IDE, cloud, and API access. |

Set `model_catalog_json` as a top-level requirement before any TOML table headers. On macOS, a managed requirements file can use:

```toml
# requirements.toml - keep Codex updated through approved device management
model_catalog_json = "/etc/codex/approved-models.json"
```

On native Windows, use the equivalent protected local device path:

```toml
# requirements.toml - keep Codex updated through approved device management
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

On Windows, replace the catalog path with the single-quoted Windows path shown above. A `model_catalog_json` setting that appears only in client configuration remains a client preference. Put the matching setting in managed requirements when the catalog must be enforced.

### Apply different model policies to enterprise groups

When different teams require different approved models, create a reviewed catalog and managed policy for each risk group. Assign the relevant cloud-managed requirements policy to the intended enterprise users or groups, distribute its matching protected catalog through device management, and verify that pilot users receive the expected model picker. Confirm that users outside the target group retain their intended policy and review source precedence when system, cloud-managed, or MDM requirements also apply.

Group assignment controls which catalog policy a Codex user receives. It does not replace workspace entitlements, backend authorization, or the organization's identity-provider access controls. Managed new-thread model defaults can establish a preferred starting model, but they remain defaults and do not replace an enforced catalog.

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

The example model is illustrative and must be verified against the organization's approved model list, current entitlement, and deployed client. Maintain the catalog as a reviewed enterprise artifact, refresh it when approved models change, and pilot the policy with the intended user group before wider rollout.

An enforced catalog governs the Codex catalog and model picker. It does not establish a backend authorization boundary or prevent a different product surface or API credential from reaching a model that the backend still authorizes. When a model must be inaccessible rather than hidden from normal selection, require the corresponding server-side administrative or entitlement control and verify its effective behavior.

## Review the major governance decisions

### Identity, workspace, and model access

Bind deployment to the correct enterprise tenant through the organization's identity provider, provisioning process, and approved ChatGPT workspace. Use the managed `allowed_login_methods = ["chatgpt"]` requirement to prevent API-key or other unapproved login modes. When enterprise workspace binding is required, configure `allowed_chatgpt_workspaces` with independently verified production identifiers and align the optional `forced_chatgpt_workspace_id` client setting with that allowlist. Never copy an example, customer, or unverified workspace identifier into production.

Keep `model_reasoning_effort` aligned with latency, cost, and workload needs. For managed catalog restrictions, keep all targeted clients updated and use the supported `model_catalog_json` requirement. Actual model authorization, provider approval, account entitlements, and contractual data-processing conditions still require their own supported administrative controls. Do not invent an unsupported `allowed_models` requirement.

### Permission profiles for different enterprise groups

The reference policy includes an inspection-only `regulated_read_only` profile and a default `regulated_workspace` profile with command networking disabled. Assign the narrowest profile that supports each approved workflow.

Organizations that require access to approved registries or internal services can create a separate reviewed network-enabled profile with explicit domain allowlists. Keep that profile unavailable until its destinations, data flows, ownership, and monitoring are approved. Do not use unrestricted global network allowlists, make an internet-enabled profile the default, or grant write access to protected `.git`, `.agents`, or `.codex` paths without a separately approved security requirement.

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

Do not assume a TOML setting establishes EU residency or satisfies a contractual residency commitment. Check the current supported residency values and validate applicable data-processing controls separately with the enterprise administrators and legal or security owners.

### Filesystem access as one part of the policy

The example extends the built-in `:workspace` profile for compatibility with ordinary development tools and adds global managed `deny_read` protections for SSH keys, cloud credentials, package-manager configuration, container credentials, and certificate material. A workspace profile can still inherit broader filesystem reads than a dedicated read-isolation policy. When an organization must prevent access to network shares or other directories, define explicit readable roots with a stricter custom profile and enforce the same boundary through operating-system and endpoint controls.

A selected workspace is trusted by its workspace profile. If a prohibited network share is selected as the workspace, the profile includes that share by definition. Prevent prohibited workspace selection through identity, endpoint, operating-system, or file-share policy.

On Windows, managed `deny_read` restrictions protect direct file tools, but shell subprocess reads do not use that same restriction. Wildcard rules are expanded against existing files and use the configured scan depth. The explicit `.env` and `.env.local` entries protect known paths, but deeper files, newly created wildcard-only matches, shell access, and network shares require additional operating-system and endpoint controls.

Command-prefix rules provide an additional review boundary, and the most restrictive matching decision takes precedence. They do not semantically inspect every possible shell script. Do not treat those rules as a replacement for sandbox, endpoint, or identity controls.

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
sandbox_private_desktop = true
```

Add the matching section to the deployed `config.toml` to select that implementation and keep private-desktop isolation enabled:

```toml
[windows]
sandbox = "elevated"
sandbox_private_desktop = true
```

`elevated` describes the preferred Windows sandbox implementation and setup; it does not grant the agent unrestricted administrator privileges. Administrators may need to approve endpoint prerequisites, local sandbox-user creation, privilege-management compatibility, or firewall configuration.

If enterprise endpoint controls prevent elevated setup, use the `unelevated` sandbox only as an explicitly approved exception. Keep `sandbox_private_desktop = true` in both managed requirements and client configuration, document the weaker isolation, add compensating endpoint and network controls, assign a risk owner, and track remediation. Do not represent the fallback as equivalent to the preferred elevated sandbox.

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
sandbox_private_desktop = true
'@

Add-Content -Path $deployedConfig -Value @'

[windows]
sandbox = "elevated"
sandbox_private_desktop = true
'@
```

The system requirements path is `%ProgramData%\OpenAI\Codex\requirements.toml`; the user configuration path is `%USERPROFILE%\.codex\config.toml`. Prefer the organization's standard endpoint-management tooling for production rollout.

Keep the managed sandbox implementation, enforced private-desktop setting, and matching client defaults aligned. Verify the latest supported Windows configuration reference before distributing a new policy.

## Compare deployment approaches

| Configuration source | macOS | Native Windows |
| --- | --- | --- |
| Enforced system requirements | `/etc/codex/requirements.toml` | `%ProgramData%\OpenAI\Codex\requirements.toml` |
| User configuration | `~/.codex/config.toml` | `%USERPROFILE%\.codex\config.toml` |
| Managed defaults | `/etc/codex/managed_config.toml` or macOS MDM | `~/.codex/managed_config.toml` or approved device management |
| MDM requirements | `com.openai.codex:requirements_toml_base64` | Not applicable |
| MDM defaults | `com.openai.codex:config_toml_base64` | Not applicable |
| Platform sandbox | Native macOS sandbox | Preferred elevated Windows sandbox; reviewed fallback only |

Where supported, enterprise administrators can also assign cloud-managed requirements to specific user groups. Start with a pilot group, verify the effective policy for pilot and non-pilot users, and resolve precedence between cloud-managed, system, and MDM sources before broader deployment.

## Validate the examples and rollout

The example directory includes a validator that uses a current Python release and the standard library:

```bash
python examples/codex/regulated_industry_configuration/validate_blueprints.py
```

Expected output:

```text
PASS general: requirements.toml, config.toml
Validated 1 blueprint pair for the latest Codex release.
```

The validator checks enterprise approval boundaries, allowed operating modes, web-search governance, permission profiles, MCP restrictions, managed features, change-control rules, identity and credential defaults, analytics, history, and observability.

After enabling an approved model catalog on a supported client, validate the deployed files, client version, selected model, permitted reasoning levels, and catalog contents together:

```bash
python examples/codex/regulated_industry_configuration/validate_blueprints.py \
  --requirements /etc/codex/requirements.toml \
  --config "$HOME/.codex/config.toml" \
  --model-catalog /etc/codex/approved-models.json
```

For Windows, use `--platform windows` and replace the three file paths with the corresponding `%ProgramData%` and `%USERPROFILE%` deployment locations.

For a documented and security-approved unelevated Windows exception, add `--allow-windows-fallback` when validating the deployed Windows files. This flag makes the exception explicit; it does not strengthen the fallback sandbox.

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

Validate the policy that actually reaches each managed device. Export or inspect the active requirements in the supported management interface, compare them with the intended files, and identify the effective cloud-managed, system, or MDM source. Do not treat an email attachment, copied chat snippet, cached policy fragment, or reconstructed configuration as proof of the active enterprise policy.

After deploying a pilot:

1. Confirm every local client uses the latest approved release and can enforce the deployed policy.
2. Open `/debug-config` and verify the active requirements source, approval settings, and selected permission profile.
3. Confirm the correct enterprise authentication flow, workspace, credential store, and permitted integrations.
4. If a managed model catalog is enabled, verify the active policy source, approved models, reasoning levels, protected catalog path, and backend model entitlements.
5. Check web-search mode, command networking, analytics, local history, and approved telemetry settings.
6. Validate that sensitive development actions prompt for review and protected production actions are forbidden.
7. On Windows, confirm the elevated sandbox initializes or verify that an explicitly approved fallback has compensating controls and a remediation owner.
8. If investigation is required, run `/feedback` in the active session and share the resulting feedback ID through the approved support process.

Do not include raw credentials, customer data, confidential source code, or other sensitive material in support messages.

## Adapt the baseline to the organization

Use one managed baseline as the starting point, then create reviewed variations for distinct risk groups. A software engineering group might permit cached search and approved repository integrations, while a production-support group could use read-only permissions and a no-exception approval policy.

Review each change across the full operating model: identity, human oversight, execution, network access, integrations, sensitive data, auditability, and endpoint controls. Keep all Codex surfaces on the latest approved release, synchronize the two shared files, avoid unverified identifiers, inspect the effective managed policy, and validate any Windows-only settings added during deployment.

## References

- [Managed configuration and enterprise requirements](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [Enterprise login and workspace authentication controls](https://learn.chatgpt.com/docs/auth#enforce-a-login-method-or-workspace)
- [Workspace model availability and administrative controls](https://learn.chatgpt.com/docs/enterprise/workspace-model-availability)
- [Permission profiles and execution boundaries](https://learn.chatgpt.com/docs/permissions)
- [Native Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Managed execution rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
