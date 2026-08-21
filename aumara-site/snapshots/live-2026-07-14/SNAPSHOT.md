# AUMARA live snapshot — 2026-07-14

Purpose: preserve the exact public AUMARA HTML before the preview reconciliation. This snapshot is evidence and a recovery reference, not the production source.

## Captured source

- Public path: `https://elcidspain.com/aumara/`
- Snapshot file: `index.html`
- Capture date: 2026-07-14
- HTML SHA-256: `6f2c6869f16ef52b493ceac84b279ecd048e8a15bd7b4e980a49a7f1d9e4a368`

## Route media verification

The live page referenced eight relative route clips under `media/nodes/`. Exact copies were captured and verified locally before reconciliation. They are not added to this review commit; stable production media migration remains a separate gate.

- `node-01.mp4` — `e109807b7785ac8af0fb42c85b1f20d5bad6286bbe5282078b4c1ee4197ed7f4`
- `node-02.mp4` — `f06c0f82762cea241aa39e635163c59ac05c1305a2ff177a5501ab030f10c2bb`
- `node-03.mp4` — `36e1b475bbcd3aaaabd167ff8e45bb7053dc38363cc4cfd10a259c9b2f816851`
- `node-04.mp4` — `5842f4cfa2ba5b75c71c8e130431dfbd68573cfa0f1bc0f48140c3000222b7c6`
- `node-05.mp4` — `49b68abb385853a031cc758a9a6e0bebc6e61d34f20b033c9263ec91ec718141`
- `node-06.mp4` — `f2784b7f7425a1b66cfb2fdaf51b18996be5bfb3a0af7c359f6de85b2a2a9d79`
- `node-07.mp4` — `b56f8f3c961ac198aaddcb466d38316ac363c2d1bb5bc3748063d809cc1d3711`
- `node-08.mp4` — `2c347a7a5d332b0c6854703337230c6538d565cc735867931d8472f71c3d9d27`

## Recovery note

The production file `aumara-site/index.html` is deliberately outside this snapshot and is not changed by the reconciliation PR. The reviewed implementation lives in `aumara-site/direct-v3-preview.html`.
