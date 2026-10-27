# Security review: October 27, 2026

This is a scoped review, not a security certification.

## Credentials and data flow

Manual review and credential-pattern scans found no real embedded credentials
in the 14 tracked Decisions example files or generated JSON/HTML reports. Test
credentials are fabricated placeholders. The API key comes from
`OPENAI_API_KEY` or hidden Terminal input; it is not written to source,
configuration, or an environment file, or passed as a CLI argument.

The shell wrapper disables tracing before inspecting the key, applies
`umask 077`, and clears its key after use. A key exported by the invoking shell
remains in that parent shell until the user unsets it. Existing local
`.generated/` and `.local/` artifacts were restricted to the current user.
Both paths, `.env`, and `node_modules/` are ignored by Git.

API requests use the explicitly configured `https://api.openai.com/v1` endpoint.
Dataset downloads use a pinned GitHub commit and verified SHA-256 hashes.
Only customer-message text is rendered into input; expected labels remain in
the local grader. The fixed JavaScript assertion parses response JSON rather
than executing model output. The runners execute trusted local notebook code;
they must not be used with an unreviewed notebook.

The wrapper disables Promptfoo telemetry and update checks, and configures
`sharing: false`. It does not sign in to Cloud or publish reports. Local reports
contain public messages and their responses.

## Unresolved dependency findings

`npm audit --json` reported nine high-severity affected package entries from
three underlying advisories, with zero critical findings. Transitive entries
are not nine independent vulnerabilities. Promptfoo is pinned to `0.124.1`.

| Dependency | Locked version | Advisory | Patch situation |
| --- | --- | --- | --- |
| `@azure/msal-node` | `6.0.1` | [GHSA-xcx6-jx8p-x3h5](https://github.com/advisories/GHSA-xcx6-jx8p-x3h5) | Patch `7.1.0` is outside `@azure/identity`'s `^6.0.0` range |
| `basic-ftp` | `5.3.1` | [GHSA-c475-qrg2-pj4r](https://github.com/advisories/GHSA-c475-qrg2-pj4r) | Patch `6.2.1` is outside `get-uri`'s `^5.3.1` range |
| `node-forge` | `1.4.0` | [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) | No patched release listed |

This example does not configure Azure OAuth, FTP sources, or JKS keystores.
That is not proof of non-exploitability or an approved risk exception. No blind
major-version override or `npm audit fix --force` was applied. Recheck upstream
fixes and involve the maintainer before treating the companion as dependency-clean
or ready for approval. The standard-library notebook/runner does not require
Promptfoo or these npm dependencies.

Repeat the dependency check from this directory with `npm audit --json`.

## Dataset terms

The publisher's [README](https://github.com/PolyAI-LDN/task-specific-datasets/blob/57ec275d8078af65b7731c2a98be812d844a6d6b/README.md)
applies the repository's
[CC BY 4.0 license](https://github.com/PolyAI-LDN/task-specific-datasets/blob/57ec275d8078af65b7731c2a98be812d844a6d6b/LICENSE)
to the dataset. The companion includes attribution, the paper citation, the
license text, and our subset/label modifications. This example uses the public
benchmark, not OpenAI records or private customer messages. The license does not
grant privacy/publicity rights or constitute blanket internal authorization for
other data. Replacement private/customer data requires the applicable authorization.
