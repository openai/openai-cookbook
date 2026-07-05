# AUMARA TTLock Gateway Mesh v0.1

Date: 2026-07-05
Owner: Ilya / Onsite Tech

## Decision

Use a distributed TTLock gateway layout, not one central gateway.

The AUMARA houses are separate buildings spread across roughly 30 metres. TTLock documents a maximum G2 range of about 10 metres with no obstruction, so the operating design should target 5–8 metres and no more than one major wall between a gateway and a lock.

## Target architecture

- Three active TTLock G2 Wi-Fi gateways across the AUMARA house cluster.
- One additional unit kept as a spare or used for a common entrance if the missing original gateway is recovered.
- Every gateway connects independently to stable 2.4 GHz property Wi-Fi.
- Each gateway bridges nearby locks to the TTLock cloud; gateways do not relay through one another.

## Procurement

Buy two additional gateways now. Required specification:

- explicit TTLock app compatibility;
- G2 Wi-Fi Gateway or seller-confirmed TTLock G2 equivalent;
- 2.4 GHz Wi-Fi;
- EU-compatible USB power;
- not Tuya-only, TTHotel-only, Zigbee-only or proprietary-brand-only.

## Deployment

1. Resolve the physical five-versus-six house map.
2. Confirm the existing white device model.
3. Add all gateways to the corporate TTLock master account.
4. Place gateways by real signal tests, not by drawing alone.
5. Test every lock remotely with phone Bluetooth disabled and phone on mobile data.
6. Record the final house, lock and gateway mapping.
7. Run the Beds24 create, modify and cancel booking test.

## Acceptance criteria

Every live house must have:

- confirmed physical identity;
- correct TTLock name;
- corporate ownership;
- an online assigned gateway;
- stable remote lock control;
- remotely visible battery and status;
- timed PIN create, update and revoke tested;
- mechanical key fallback recorded;
- correct Beds24 mapping and lifecycle test passed.

Beds24 to TTLock automation remains RED until all tests pass.
