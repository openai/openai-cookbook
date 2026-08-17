# Policy Registry Changelog

## Guest journey snapshot 2026.08.17.2 — 2026-08-17

- Added proposal-only post-check-in and first-morning care messages for AUMARA and EL CID.
- Added English, Spanish, French, German and Dutch policy templates.
- Hard-blocked checkout pressure and departure-deadline messages.
- Added in-house status, Europe/Madrid time-window, departure-day, incident,
  negative-signal and stable lifecycle deduplication gates.
- Made structured incidents and new guest complaints override lifecycle
  deduplication, and suppressed duplicate proposals within one batch.
- Added an hourly Beds24 GET-only shadow mapper with aggregate PII-free output.
- Kept guest sends, Beds24 actions and booking mutations structurally disabled.
- Kept global policy version `2026.07.27.1` compatible with existing live note workers.

## Guest reply snapshot 2026.08.02.1 — 2026-08-02

- Added verified EL CID reply fragments for large-double-bed, parking and non-smoking requests.
- Fixed the non-smoking rule as a confirmed property fact rather than an availability-dependent preference.
- Added multilingual registry templates and a fail-closed runtime loader.
- Added a delivery-failure rule that preserves approved reply content when Workspace, Gmail or connector delivery fails.
- Added a Pedro-style regression proving the generated reply contains no `subject to availability` fallback.
- Synchronized the live ChatGPT guest-reply automation prompt to snapshot version `2026.08.02.1`.
- Kept global policy version `2026.07.27.1` compatible with existing live Beds24 workers.

## 2026.07.27.1 — 2026-07-27

- Created separate shared, EL CID, and AUMARA registries.
- Added a shared schema and fail-closed cross-file validation.
- Added source-reference placeholders without private operational values.
- Added focused tests for versioning, product separation, automation guards,
  and sensitive-value rejection.
