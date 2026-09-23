#!/usr/bin/env python3
"""Build exact, accessible SVG and Mermaid figures using only the standard library.

No fonts, logos, browser packages, model calls or network access are required.
The restrained system-font design is not a claim of official brand approval.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from html import escape
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ASSET_NAME = "governed_repository_security_reviews"
SOURCE_PATHS = (
    "src/fleet_security/pipeline.py",
    "src/fleet_security/threats.py",
    "src/fleet_security/recipe.py",
    "src/fleet_security/scanner.py",
    "src/field_autonomy/sandbox.py",
)
IDEMPOTENCY_FIELDS = (
    "repository_id", "commit_sha", "effective_threat_model_hash",
    "scanner_version", "policy_version",
)
SCOPE_FIELDS = ("repository_id", "commit_sha", "owner")
PALETTE = {
    "background": "#FAFBF9", "ink": "#19211F", "muted": "#48534F",
    "rule": "#BAC5BE", "accent": "#296348", "tint": "#EDF4EF",
}


def text(x: int, y: int, value: str, *, size: int = 22, weight: int = 400,
         fill: str = "#19211F") -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{escape(value)}</text>'
    )


def lines(x: int, y: int, values: tuple[str, ...], *, size: int = 21,
          leading: int = 31) -> str:
    return "".join(text(x, y + index * leading, value, size=size, fill=PALETTE["muted"])
                   for index, value in enumerate(values))


def rectangle(x: int, y: int, width: int, height: int, *, fill: str = "#FFFFFF",
              stroke: str = "#BAC5BE", dashed: bool = False, radius: int = 12) -> str:
    dash = ' stroke-dasharray="10 7"' if dashed else ""
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.8"{dash}/>')


def arrow(path: str, *, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="9 7"' if dashed else ""
    return (f'<path d="{path}" fill="none" stroke="#48534F" stroke-width="2.4" '
            f'stroke-linejoin="round" marker-end="url(#arrow)"{dash}/>')


def svg_document(title: str, description: str, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" role="img" aria-labelledby="diagram-title diagram-description">
  <title id="diagram-title">{escape(title)}</title>
  <desc id="diagram-description">{escape(description)}</desc>
  <defs>
    <marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 9 4.5 L 0 9 z" fill="#48534F"/></marker>
  </defs>
  <rect width="1600" height="900" fill="{PALETTE['background']}"/>
  <g font-family="Arial, Helvetica, sans-serif">
    {body}
  </g>
</svg>
'''


def architecture_svg() -> str:
    title = "Governed security review architecture"
    description = (
        "Five solid-arrow stages show the optional Docker path of the synthetic reference. "
        "Trusted inventory and policy require a named scope approver for the repository, commit and current owner. "
        "The trusted host rechecks scope and high-risk context, then applies rate, worker and admission budgets. "
        "It launches separate network-denied, non-root Docker fixture workers with read-only source and no secrets. "
        "The host validates findings, coverage, manifest, hashes and HMAC state before named human disposition and a private review packet. "
        "A dashed alternative through a future Codex Security CLI or SDK adapter is not executed and needs separately approved identity, model egress and spend. "
        "The daemon-free Compose service has only its outer container boundary; it does not launch a separate inner worker. "
        "Idempotency binds repository ID, commit SHA, effective context hash, scanner version and policy version. Scope separately binds the current owner."
    )
    body = text(48, 77, "Governed security reviews", size=44, weight=600)
    body += text(48, 119, "Trust boundaries for the optional restricted-Docker demonstration", size=24, fill=PALETTE["muted"])
    body += arrow("M 50 169 L 101 169")
    body += text(116, 177, "Implemented with synthetic fixtures", size=21)
    body += arrow("M 686 169 L 737 169", dashed=True)
    body += text(752, 177, "Future live integration — not executed", size=21)
    body += rectangle(32, 217, 608, 346, fill="#F2F5F1", radius=16)
    body += rectangle(648, 217, 296, 346, fill=PALETTE["tint"], stroke=PALETTE["accent"], radius=16)
    body += rectangle(952, 217, 608, 346, fill="#F2F5F1", radius=16)
    body += text(54, 249, "TRUSTED HOST", size=17, weight=600, fill=PALETTE["muted"])
    body += text(667, 249, "SEPARATE WORKERS", size=17, weight=600, fill=PALETTE["accent"])
    body += text(974, 249, "TRUSTED HOST", size=17, weight=600, fill=PALETTE["muted"])
    cards = (
        (48, 272, "01", "Authorise scope", ("Inventory + policy", "Repo ID · full SHA", "Current owner", "Named scope approver")),
        (352, 272, "02", "Admit work", ("Scope rechecked", "High-risk context gate", "Rate · budget · workers", "Reuse eligible evidence")),
        (664, 264, "03", "Fixture workers", ("Host-launched Docker", "No network · non-root", "Read-only source", "No secrets · zero caps")),
        (968, 272, "04", "Verify evidence", ("Findings + coverage", "Manifest + hashes", "HMAC state + audit", "Invalid evidence → stop")),
        (1272, 272, "05", "Named review", ("Disposition findings", "Private review packet", "Patch needs approval", "No merge or deploy")),
    )
    for x, width, number, heading, details in cards:
        body += rectangle(x, 279, width, 252, stroke=PALETTE["accent"] if number == "03" else PALETTE["rule"])
        body += text(x + 21, 315, number, size=17, weight=600, fill=PALETTE["accent"])
        body += text(x + 21, 354, heading, size=24, weight=600)
        body += lines(x + 21, 397, details, size=20, leading=31)
    for start, end in ((320, 352), (624, 664), (928, 968), (1240, 1272)):
        body += arrow(f"M {start} 405 L {end} 405")
    body += arrow("M 488 531 L 488 590 L 620 590 L 620 620", dashed=True)
    body += arrow("M 1120 682 L 1188 682 L 1188 581 L 1104 581 L 1104 531", dashed=True)
    body += rectangle(480, 620, 640, 128, fill="#FAFBF9", stroke="#65786D", dashed=True)
    body += text(510, 655, "Future Codex Security adapter", size=26, weight=600)
    body += lines(510, 692, ("CLI / SDK · not executed by this example", "Separate approved identity, model egress and spend"), size=21, leading=29)
    body += text(48, 790, "Daemon-free Compose confines one service; it does not create a separate inner worker.", size=21, fill=PALETTE["muted"])
    body += text(48, 836, "Idempotency: repo ID + commit SHA + effective context hash + scanner version + policy version.", size=21, weight=600)
    body += text(48, 870, "Scope also binds the current owner. Missing approval or invalid evidence stops dispatch.", size=21, fill=PALETTE["muted"])
    return svg_document(title, description, body)


def threat_context_svg() -> str:
    title = "Versioned threat context and human acceptance"
    description = (
        "Organisation baseline, workload archetype and individual repository delta feed an effective context hash. "
        "A bespoke repository model contributes for the high-risk tier. "
        "The digest binds catalogue version, strategy, organisation controls, archetype, repository model, delta and covered scenario metadata. "
        "High-risk repositories require a named human to accept that exact hash; missing or stale acceptance holds work. "
        "Other repositories reach admission directly, while scope approval remains independently required for all repositories. "
        "Admission rechecks approvals before queuing work or reusing current evidence. "
        "A baseline change can alter every repository hash, so editing one shared artefact may invalidate all repositories. "
        "This is deterministic context metadata, not generated or empirically validated threat-model prose."
    )
    body = text(64, 77, "Versioned threat context", size=44, weight=600)
    body += text(64, 119, "Reuse shared controls without losing repository-specific boundaries", size=24, fill=PALETTE["muted"])
    body += text(64, 178, "TRUSTED CONTEXT INPUTS", size=18, weight=600, fill=PALETTE["accent"])
    inputs = (
        (64, "Organisation baseline", ("Version + shared controls", "Identity · network · data · audit")),
        (568, "Workload archetype", ("Reviewed reusable pattern", "Topology · exposure · framework")),
        (1072, "Repository delta", ("Data · authentication · dependencies", "Criticality · controls · divergence")),
    )
    for x, heading, details in inputs:
        body += rectangle(x, 217, 464, 164)
        body += text(x + 26, 260, heading, size=27, weight=600)
        body += lines(x + 26, 305, details, size=23, leading=34)
    body += '<path d="M 296 381 V 409 H 1304 V 381 M 800 381 V 409" fill="none" stroke="#48534F" stroke-width="2.4"/>'
    body += arrow("M 800 409 L 800 448")
    body += rectangle(64, 448, 464, 158)
    body += text(90, 490, "Bespoke high-risk context", size=27, weight=600)
    body += lines(90, 533, ("Trusted repository-specific model", "Required for the high-risk tier"), size=23, leading=34)
    body += arrow("M 528 528 L 568 528")
    body += rectangle(568, 448, 464, 158, fill=PALETTE["tint"], stroke=PALETTE["accent"])
    body += text(594, 490, "Effective context hash", size=27, weight=600)
    body += lines(594, 533, ("Versioned composition of the inputs", "An input change changes the digest"), size=23, leading=34)
    body += arrow("M 1032 528 L 1072 528")
    body += rectangle(1072, 448, 464, 158)
    body += text(1098, 480, "HIGH RISK: NAMED REVIEW", size=17, weight=600, fill=PALETTE["accent"])
    body += text(1098, 519, "Accept the exact hash", size=27, weight=600)
    body += lines(1098, 562, ("Missing or stale approval → hold",), size=23)
    body += arrow("M 800 606 L 800 688")
    body += text(816, 650, "Other repositories", size=20, fill=PALETTE["muted"])
    body += arrow("M 1304 606 L 1304 740 L 1032 740")
    body += text(1094, 723, "Accepted hash", size=20, fill=PALETTE["muted"])
    body += rectangle(568, 688, 464, 110)
    body += text(594, 731, "Admission rechecks approval", size=26, weight=600)
    body += text(594, 771, "Queue work or reuse current evidence", size=22, fill=PALETTE["muted"])
    body += rectangle(64, 827, 1472, 62, fill="#EDF4EF", stroke="#EDF4EF", radius=8)
    body += text(84, 852, "A baseline change can invalidate every repository.", size=22, weight=600)
    body += text(84, 879, "One edited model artefact can require many new reviews; context reuse does not remove revalidation.", size=20, fill=PALETTE["muted"])
    return svg_document(title, description, body)


ARCHITECTURE_MERMAID = '''flowchart LR
    accTitle: Governed security review architecture
    accDescr: Solid arrows show synthetic fixture execution with optional separate Docker workers. Dashed arrows show a future unexecuted product adapter. Scope binds repository, revision and current owner. Named humans retain disposition, patch, merge and deploy authority.
    subgraph host_in[Trusted host: authority and admission]
        scope[Trusted inventory and policy<br/>Named scope approval<br/>Repo ID + full SHA + current owner]
        admit[Host admission<br/>Scope and risk-context checks<br/>Rate, budget, workers and idempotency]
        scope --> admit
    end
    subgraph worker[Separate optional Docker workers]
        fixture[Read synthetic fixtures<br/>No network, non-root, read-only source<br/>No secrets or Docker socket]
    end
    subgraph host_out[Trusted host: evidence and review]
        evidence[Findings, coverage and manifest<br/>Hashes, HMAC state and audit<br/>Invalid evidence stops dispatch]
        human[Named finding disposition<br/>Private review packet<br/>Patch approval; human-only merge/deploy]
        evidence --> human
    end
    admit --> fixture --> evidence
    future[Future Codex Security CLI / SDK adapter<br/>NOT EXECUTED<br/>Separate approved identity, model egress and spend]
    admit -. proposed live path .-> future -. verified output contract .-> evidence
    note[Daemon-free Compose confines one service;<br/>it does not create a separate inner worker.]
    classDef muted fill:#fafbf9,stroke:#65786d,color:#19211f,stroke-dasharray:9 7;
    classDef safe fill:#edf4ef,stroke:#296348,color:#19211f;
    class future,note muted;
    class fixture safe;
'''

THREAT_MERMAID = '''flowchart TD
    accTitle: Versioned threat context and human acceptance
    accDescr: Organisation baseline, archetype, repository delta and bespoke high-risk context form an effective hash. Named humans must approve the exact hash for high-risk repositories. A baseline edit can invalidate all repository hashes despite changing a single shared artefact.
    org[Organisation baseline<br/>Version and shared controls]
    archetype[Workload archetype<br/>Topology, exposure and framework]
    delta[Repository delta<br/>Data, auth, dependencies, criticality,<br/>additional controls and divergence]
    bespoke[Bespoke high-risk context<br/>Trusted repository-specific model]
    digest[Effective context hash<br/>Versioned composition of trusted inputs]
    approval[High risk: named human accepts exact hash<br/>Missing or stale approval holds work]
    admit[Admission rechecks approvals<br/>Queue work or reuse current evidence]
    org --> digest
    archetype --> digest
    delta --> digest
    bespoke --> digest
    digest -->|high risk| approval -->|accepted| admit
    digest -->|other repositories| admit
    note[Baseline change can invalidate every repository.<br/>One edited artefact can require many new reviews.]
    classDef safe fill:#edf4ef,stroke:#296348,color:#19211f;
    class digest,note safe;
'''


DIAGRAM_NOTES = '''# Technical diagram sources and text alternatives

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
'''


def validate_source_contracts() -> dict[str, str]:
    tree = ast.parse((ROOT / SOURCE_PATHS[0]).read_text(encoding="utf-8"))
    for method_name, expected in (("_idempotency_key", IDEMPOTENCY_FIELDS), ("scope_target", SCOPE_FIELDS)):
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == method_name)
        mapping = next(node for node in ast.walk(method) if isinstance(node, ast.Dict))
        fields = tuple(key.value for key in mapping.keys if isinstance(key, ast.Constant))
        if fields != expected:
            raise ValueError(f"diagram contract is stale: {method_name}")
    return {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in SOURCE_PATHS}


def assets() -> dict[str, str]:
    source_hashes = validate_source_contracts()
    result = {
        "architecture.svg": architecture_svg(), "threat_context.svg": threat_context_svg(),
        "architecture.mmd": ARCHITECTURE_MERMAID, "threat_context.mmd": THREAT_MERMAID,
        "DIAGRAMS.md": DIAGRAM_NOTES,
    }
    svg_checks = {}
    for name in ("architecture.svg", "threat_context.svg"):
        document = ElementTree.fromstring(result[name])
        namespaces = {"svg": "http://www.w3.org/2000/svg"}
        for label in ("title", "desc"):
            element = document.find(f"svg:{label}", namespaces)
            if element is None or not element.text:
                raise ValueError(f"missing accessible {label}: {name}")
        if any(item.tag.rsplit("}", 1)[-1] in {"script", "image", "foreignObject"}
               for item in document.iter()):
            raise ValueError(f"unexpected active or external SVG content: {name}")
        svg_checks[name] = {"xml_parsed": True, "accessible_title_and_description": True,
                           "text_elements": len(document.findall(".//svg:text", namespaces)),
                           "external_resources": False}
    manifest = {
        "format": "governed-security-cookbook-diagrams/v1",
        "method": "deterministic_code_native_svg_and_mermaid",
        "image_generation_model": None, "paid_generation_calls": 0,
        "sharing_status": "publication_candidate_not_published",
        "brand_source": "https://openai.com/brand/",
        "exact_brand_certification": False,
        "asset_discovery": "no approved redistributable font or logo selected; system-font fallback",
        "font_stack": ["Arial", "Helvetica", "sans-serif"],
        "embedded_fonts": False, "logos": False,
        "viewbox": [0, 0, 1600, 900],
        "idempotency_fields": list(IDEMPOTENCY_FIELDS), "scope_approval_fields": list(SCOPE_FIELDS),
        "source_sha256": source_hashes,
        "asset_sha256": {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                         for name, content in result.items()},
        "verification": svg_checks,
        "visual_review": "inspect rendered previews separately; structural checks are not visual QA",
        "limitations": ["synthetic control path only", "future product adapter is not executed",
                        "Compose outer containment is distinct from separately launched Docker workers",
                        "one baseline change may invalidate every repository", "no exact brand certification"],
    }
    result["asset-manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return result


def default_output_directory() -> Path:
    if ROOT.parent.name == "codex" and ROOT.parent.parent.name == "examples":
        return ROOT.parents[2] / "images" / ASSET_NAME
    return ROOT / "images" / ASSET_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_directory())
    parser.add_argument("--check", action="store_true", help="Verify exact existing assets without writing.")
    arguments = parser.parse_args()
    expected = assets()
    if arguments.check:
        for name, content in expected.items():
            path = arguments.output_dir / name
            if not path.is_file() or path.is_symlink() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"missing or changed diagram asset: {name}")
    else:
        arguments.output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in expected.items():
            destination = arguments.output_dir / name
            if destination.is_symlink():
                raise ValueError(f"refusing a linked diagram output: {name}")
            destination.write_text(content, encoding="utf-8")
    print(json.dumps({"diagrams": 2, "assets": len(expected), "verification": "PASS",
                      "check_only": arguments.check, "paid_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
