# AUMARA fixed guest PIN — operating mode

**Effective:** 2026-08-03  
**Owner:** Ilya / Control Tower  
**PIN:** `1531` + `#`

## Decision

Stop depending on Beds24 TTLock Offline unique codes for guest communication.
Every guest of every AUMARA unit receives the same permanent code: **1531**.

## Why

- All locks `hasGateway: 0` → Marketplace remote sync fails (`Device is not connected to any Gateway`)
- Offline auto codes change per booking and cannot be forced permanent
- Permanent keypad code already exists operationally (`1531`); ship that

## What Control Tower does

1. Guest access email template defaults to `1531` when no override is supplied
2. Access audit expects message text to contain `1531` (fixed-pin mode)
3. Seed job writes booking infoItem `LOCK_PIN` = `1531` so Beds24 placeholders resolve to the fixed code
4. Lock registry documents numeric lockIds (never device name as lockId)

## What must be true on the physical locks

On every house lock, permanent passcode **1531** must open the door (Bluetooth admin setup once per lock if missing). Guest instruction: enter `1531` then `#`.

## Beds24 Auto Action text (canonical)

```
Código de acceso al chalet: 1531
Introduzca 1531 y pulse #
Check-in: 16:00 · Check-out: 12:00
```

Prefer fixed text over `[BOOKINGINFOCODETEXT:LOCK_PIN]`. If the placeholder is kept, seed job keeps `LOCK_PIN=1531`.

## Security note

Shared PIN is weaker than per-booking codes. Mechanical key remains fallback. When gateways are online, re-evaluate unique/online PINs.
