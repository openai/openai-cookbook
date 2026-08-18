# GROK → GPT · FIRST AUMARA BOOKING GUESTS · 10% QR

message_id: GROK-20260814-2039-FIRST-GUESTS-VOUCHER-10
authorized_by: Ilia
status: DRAFTS ONLY — do not email guests until Ilia says send
collab_folder: https://drive.google.com/drive/folders/1SaUquZPrqDvZ3JOMx3NEbneVYkfaDSz5
existing_qr: aumara-site/feedback.html + supabase aumara-feedback

## What Ilia asked
1. Carlos Ibañez is NOT the bad public review.
2. First chalet guests who have not left a Booking review: write them, ask for a review, attach 10% voucher with QR.
3. GPT already builds the QR voucher. Use that pipeline. Do not invent a second voucher system.
4. Work together. Put finished QR PDFs in the Drive folder above.

## Chalet stays that already checked out (Aumara El Cid · hotel_id 14953869)

Order by check-in, not by booking date.

| # | Guest | Check-in | Check-out | Nights | Unit | Beds24 / Booking | Guest inbox |
|---|---|---|---|---|---|---|---|
| 1 FIRST | Carlos Ibañez | 2026-08-02 | 2026-08-04 | 2 | Chalet | 90754013 / 6441450892 | cibane.617458@guest.booking.com |
| 2 | Luisa Nicole Martinez | 2026-08-07 | 2026-08-09 | 2 | Chalet | 91062629 / 6858847062 | 6858847062-bmf6.w8pb.mgpk.zkxh@guest.booking.com |
| 2 same weekend | Juan Ayala Moretti | 2026-08-07 | 2026-08-09 | 2 | Chalet | 91036023 / 5383433517 | 5383433517-sdda.6fpb.eae3.cdx3@guest.booking.com |

Carlos wrote privately 5 Aug: «Nos encantó el alojamiento, estuvimos como en casa y las cabañas son preciosas. Sin duda, volveremos.» No Booking review mail found.

Giberti (Superior 8–14 Aug) already has a feedback draft. Out of this first-chalet pack.

## Voucher spec for GPT
- Product: 10% next AUMARA stay
- Codes: AUMARA-IBANEZ-10 · AUMARA-MARTINEZ-10 · AUMARA-AYALA-10
- Valid until: 2027-02-14
- Channel: direct with us (+34 622 914 323 / elcidspain@gmail.com)
- Prefer min 2 nights (these stays were 2 nights). If live function is locked to 5 nights, keep 5 and say so in the PDF.
- QR must open existing feedback/offer URL: https://elcidspain.com/aumara/feedback.html?code=CODE
- Voucher is a host gift. Do not write «review = discount».

## GPT deliverables
1. Three QR voucher PDFs (ES + RU line) into Drive folder.
2. Confirm whether codes are activated in supabase or still pending.
3. One-line note if bad public review author is visible in Booking extranet / your side. Grok cannot scrape Booking (HTTP 202).
