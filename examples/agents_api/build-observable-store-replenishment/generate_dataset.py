"""Generate the deterministic dataset for the replenishment example."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATASET_VERSION = 1


def dataset() -> dict[str, Any]:
    """Return one small, deterministic retail replenishment incident."""

    return {
        "inventory.json": [
            {
                "store_id": "store_101",
                "store_name": "Lakeside Market",
                "sku": "water_24pk",
                "product_name": "Bottled water, 24 pack",
                "shelf_units": 4,
                "shelf_capacity": 24,
                "backroom_units": 20,
                "updated_at": "2026-09-18T08:00:00Z",
            },
            {
                "store_id": "store_205",
                "store_name": "Hilltop Market",
                "sku": "water_24pk",
                "product_name": "Bottled water, 24 pack",
                "shelf_units": 18,
                "shelf_capacity": 24,
                "backroom_units": 70,
                "updated_at": "2026-09-18T08:00:00Z",
            },
        ],
        "demand_forecast.json": {
            "store_id": "store_101",
            "sku": "water_24pk",
            "horizon_hours": 24,
            "baseline_units": 18,
            "storm_units": 50,
            "generated_at": "2026-09-18T08:00:00Z",
        },
        "inbound_shipments.json": [
            {
                "shipment_id": "shipment_9001",
                "store_id": "store_101",
                "sku": "water_24pk",
                "units": 60,
                "baseline_arrival": "2026-09-18T20:00:00Z",
                "storm_delay_hours": 48,
                "carrier_status": "in_transit",
            }
        ],
        "weather_events.json": [
            {
                "event_id": "weather_7001",
                "store_id": "store_101",
                "type": "severe_storm",
                "severity": "severe",
                "starts_at": "2026-09-18T12:00:00Z",
                "shipment_delay_hours": 48,
                "revised_demand_units": 50,
                "message": "A severe storm delays the replenishment truck by 48 hours.",
            }
        ],
        "nearby_store_inventory.json": [
            {
                "source_store_id": "store_205",
                "destination_store_id": "store_101",
                "sku": "water_24pk",
                "available_transfer_units": 40,
                "travel_minutes": 35,
            }
        ],
    }


POLICY = """# Replenishment policy

1. Refill a shelf below 8 units from the same store's back room to the 20-unit
   shelf presentation target.
2. Do not exceed shelf capacity or the presentation target.
3. After an approved shelf refill, use the updated shelf and back-room counts.
4. If demand before the next inbound delivery exceeds local inventory, request an
   inter-store transfer for the projected shortfall when nearby stock is available.
5. Every inter-store transfer requires human approval.
6. Recommend `needs_human_review` when the available evidence conflicts or cannot
   support a quantity.
"""


def write_dataset(destination: Path) -> None:
    """Write the dataset to *destination*."""

    destination.mkdir(parents=True, exist_ok=True)
    for filename, payload in dataset().items():
        (destination / filename).write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    (destination / "replenishment_policy.md").write_text(POLICY, encoding="utf-8")
    (destination / "dataset_metadata.json").write_text(
        json.dumps(
            {
                "schema_version": DATASET_VERSION,
                "synthetic": True,
                "scenario": "storm_delayed_store_replenishment",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_dataset(Path(__file__).with_name("data"))
