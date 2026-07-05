# AUMARA TTLock Gateway Mesh v0.2

Date: 2026-07-05
Owner: Ilya / Onsite Tech

## Decision

Use a distributed TTLock gateway layout, not one central gateway.

AUMARA has six physical houses. Five are currently rented. The far-left ordinary chalet at approximately the 9 o'clock position on the site plan is not currently rented, but it must still be connected to the access system.

The houses are separate buildings spread across roughly 30 metres. The selected G2 product states a nominal maximum connection distance of 32 feet, approximately 9.75 metres, so the operating design should target about 5 to 8 metres with as few walls as possible between gateway and lock.

## Target architecture

- Three active TTLock G2 Wi-Fi gateways across the six-house AUMARA cluster.
- One additional unit kept as a spare or used for a common entrance if the missing original gateway is recovered.
- Every gateway connects independently to stable 2.4 GHz property Wi-Fi.
- Each gateway bridges nearby locks to the TTLock cloud; gateways do not relay through one another.

## Procurement

Buy two units of the selected G2 Smart Lock WiFi Gateway now.

- unit price: EUR 46.79;
- quantity: 2;
- total: EUR 93.58.

The selected listing explicitly states TT Lock app compatibility, 2.4 GHz Wi-Fi, remote lock control, real-time status, remote custom password setup and support for multiple locks on the same account.

## Provisional placement

- Gateway A: by the Superior Chalet cluster.
- Gateway B: under or near Chalet 2 or Chalet 3, depending on actual Bluetooth reach.
- Existing gateway: placed to cover the remaining lower or far-left chalet cluster.

Final placement is determined onsite by real signal testing, not only by the site plan.

## Deployment

1. Label all six physical houses and their locks.
2. Confirm the existing white device is a TTLock G2 gateway.
3. Add the two new gateways to the corporate TTLock master account.
4. Place one gateway by the Superior Chalets and one by Chalet 2 or Chalet 3.
5. Test every lock remotely with phone Bluetooth disabled and phone on mobile data.
6. Move gateways until all six houses have stable remote control.
7. Record the final house, lock and gateway mapping.
8. Run the Beds24 create, modify and cancel booking test.

## Acceptance criteria

Every one of the six houses must have:

- confirmed physical identity;
- correct TTLock name;
- corporate ownership;
- an online assigned gateway;
- stable remote lock control;
- remotely visible battery and status;
- timed PIN create, update and revoke tested;
- mechanical key fallback recorded;
- correct Beds24 mapping and lifecycle test passed.

Beds24 to TTLock automation remains RED until all six houses pass.
