# Replenishment policy

1. Refill a shelf below 8 units from the same store's back room to the 20-unit
   shelf presentation target.
2. Do not exceed shelf capacity or the presentation target.
3. After an approved shelf refill, use the updated shelf and back-room counts.
4. If demand before the next inbound delivery exceeds local inventory, request an
   inter-store transfer for the projected shortfall when nearby stock is available.
5. Every inter-store transfer requires human approval.
6. Recommend `needs_human_review` when the available evidence conflicts or cannot
   support a quantity.
