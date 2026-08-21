# AUMARA TTLock lock registry

Last inventory: 2026-08-03 (TTLock export JSON, operator-provided).

## Permanent guest PIN policy

- **Mode:** shared permanent guest PIN (offline-capable, no gateway required)
- **Guest PIN:** `1531` then `#` on the keypad
- **Scope:** every AUMARA house / every booking
- **Do not** use TTLock Offline auto-generated one-shot codes for guest messages
- **Do not** send admin `noKeyPwd` values to guests
- Staff admin codes remain separate on each lock; guest code is only `1531`

## Locks (5 of 6 planned houses)

| TTLock alias | lockId | lockName (device) | Beds24 room | Beds24 unit | hasGateway | battery % |
|---|---:|---|---|---:|---:|---:|
| CHALET 4 | 23903424 | M302_4c7cbf | Chalet 674465 | 1 | 0 | 75 |
| CHALET 3 | 23903418 | M302_99fa84 | Chalet 674465 | 2 | 0 | 80 |
| CHALET 2 | 23903386 | M302_f6cdfc | Chalet 674465 | 3 | 0 | 80 |
| CHALET SUPERIOR 1 | 23903314 | M302_72e7e7 | Superior Chalet 674466 | 1 | 0 | 85 |
| CHALET SUPERIOR 2 | 23903360 | M302_1d86b7 | Superior Chalet 674466 | 2 | 0 | 85 |

## Name / ID trap (Beds24 “Invalid lockId”)

Beds24 sync error `Invalid lockId M302_4c7cbf` is **not** a missing lock.
`M302_4c7cbf` is the **device lockName** of **CHALET 4**, numeric **lockId `23903424`**.

Always map by numeric lockId in Beds24 Marketplace → Synchronize:

- Unit 1 → 23903424 (CHALET 4)
- Unit 2 → 23903418 (CHALET 3)
- Unit 3 → 23903386 (CHALET 2)
- Superior Unit 1 → 23903314
- Superior Unit 2 → 23903360

## Gateway status

All five locks report `hasGateway: 0`. Remote create/delete of online codes stays RED until G2 gateways are online. Permanent guest PIN `1531` is the interim operating mode.

## Missing house

Inventory has 5 locks. Planned mesh still expects a sixth house when that lock is bound.

## Secrets policy

Never commit TTLock `lockData` blobs or per-lock admin keyboard passwords to git.
