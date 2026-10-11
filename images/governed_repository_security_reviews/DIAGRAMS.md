# Technical diagram sources and text alternatives

These figures describe the synthetic reference implementation and its proposed
integration boundary. They are not deployment evidence or official brand approval.

## Regenerate and check

From the complete reference package, use Python 3.11+:

```sh
python3 -B scripts/build_cookbook_diagrams.py
python3 -B scripts/build_cookbook_diagrams.py --check
```

In the official Cookbook layout the script finds the sibling root `images/`
directory when the sample is under `examples/codex/`. `--output-dir` may select
an explicit local destination. No model, browser, network, font or logo download
is performed. The SVGs include accessible titles and descriptions, editable text,
a fixed 1600 × 900 viewBox and no external resources. Mermaid sources provide a
second editable representation; captions below preserve the full meaning in text.

## Architecture

Trusted inventory and policy bind scope approval to repository identity, full
commit SHA and current owner. The host checks scope and required high-risk context
before admission. Its idempotency key contains **exactly** `repository_id`,
`commit_sha`, `effective_threat_model_hash`, `scanner_version` and `policy_version`.
Current owner is an additional scope-approval binding, not an invented extra field
in that idempotency key. Rate, concurrency and synthetic admission budgets remain
host controls.

The solid path shows the optional Docker fixture mode. A trusted host launches
separate non-root workers with no network, no credentials, dropped capabilities
and read-only source. The default notebook mode reads source as data without
claiming container isolation. The daemon-free Compose example contains only its
outer service boundary; it cannot launch another isolated worker and has no Docker
socket. These two deployment modes must not be conflated.

The host checks the findings, coverage, manifest, hashes and authenticated state.
Missing approval or invalid evidence stops work. Named humans disposition
consequential findings; the output is a private review packet. Patch, provider
write, merge and deployment authority do not follow from a ready packet.

The dashed Codex Security CLI/SDK branch is a **future integration**, never
executed by this example. It requires separately approved repository access,
identity, model egress and spending. It neither claims native orchestration of
this control plane nor demonstrates a live product scan.

Source contracts, relative to the example package: `src/fleet_security/pipeline.py`
(`_idempotency_key`, `scope_target`, admission and review), `recipe.py` (state and
review cycles), `scanner.py` (synthetic fixture adapter), and
`src/field_autonomy/sandbox.py` (restricted Docker runtime).

## Threat context

Organisation controls, a workload archetype and a per-repository delta form the
effective context. The delta includes data class, authentication, dependencies,
criticality, additional controls and material divergence. The high-risk tier adds
a repository model. In `src/fleet_security/threats.py`, the digest binds catalogue
version, strategy, shared controls, archetype, repository model, delta and covered
scenario metadata.

The hash exists before approval. A named human accepts that exact hash for a
high-risk repository; missing or stale acceptance holds work. Scope approval is
still required independently for every repository. Admission rechecks approvals
before dispatch or evidence reuse.

**Changing one baseline artefact can change every effective hash and invalidate
all repositories.** Reducing the number of maintained artefacts does not mean
revalidating only one repository. The diagram describes deterministic context
metadata, not model-authored threat models or independently measured detection
quality.

## Accessibility and design provenance

The figures use a neutral editorial layout, high-contrast text and one restrained
green accent. They use the system stack `Arial, Helvetica, sans-serif`; no font
files, logos, icon library or other brand assets are distributed. The public
design reference is [OpenAI brand guidance](https://openai.com/brand/).

The authoring workflow selected the code-native fallback because exact labels,
accessibility and reproducibility matter here. Local brand-asset discovery did not
supply approved redistributable assets. Exact current Brand Hub fidelity is not
claimed. No image-generation model or paid generation call was used.

`asset-manifest.json` records deterministic asset hashes, source hashes and the
structural verification performed by the generator. Human visual inspection of
rendered previews remains a separate review step; a parser passing is not visual QA.
