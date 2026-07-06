# Beds24 Cutover

Date: 2026-07-06
Status: Execution

## Objective
Activate the paid Beds24 account as the operational source of truth for AUMARA.

## Verified current map
- Beds24 account: EL CID / AUMARA
- Beds24 owner ID: 165022
- Beds24 property ID: 324882
- Booking.com property ID: 14953869
- Booking.com room ID 674465: Chalet
- Booking.com room ID 674466: Superior Chalet
- Five sellable units: three Chalet and two Superior Chalet
- Six physical houses on site
- Current error: HOTEL_ACCESS_DENIED / Request for forbidden hotel id(s)

## Sequence
1. Confirm the Beds24 account is active.
2. Save the current room and rate mapping before changes.
3. Confirm the five-unit inventory map.
4. In Booking.com Extranet open Account > Connectivity provider.
5. Select Beds24 and authorise both Reservations and Rates and Availability.
6. Return to Beds24: Settings > Channel Manager > Booking.com > Mapping.
7. Enter property ID 14953869 without spaces and refresh Connection Status.
8. Use Get Codes to map room IDs 674465 and 674466 and the available rate-plan codes.
9. Keep the rooms disabled until Price Data has been reviewed.
10. Import all upcoming Booking.com reservations.
11. Review Price Data for every mapped room.
12. Activate the connection and run one controlled availability update.
13. Test reservation, modification and cancellation.
14. Enable guest messages after the channel test passes.
15. Enable access automation only after the physical-house map is confirmed.

## Acceptance
- Connection Status shows XML Active.
- Hotel Status shows Open / bookable.
- Booking.com accepts Beds24 updates without HOTEL_ACCESS_DENIED.
- One reservation lifecycle synchronizes correctly.
- No duplicate inventory exists.
- Evidence is recorded in Airtable.
