# Store replenishment manager demo

This small web app turns the cookbook's synthetic replenishment incident into a
customer-facing manager experience. It uses the same data, tool functions, agent
instructions, and decisions as the notebook.

## Run it

From `examples/agents_api/build-observable-store-replenishment`:

```bash
uv run demo/main.py --port 8010
```

Then open [http://127.0.0.1:8010](http://127.0.0.1:8010).

The server reads `OPENAI_API_KEY` from the environment or the repository's
ignored `.env.local` file. The key never reaches the browser.

## Demo story

1. Stay in **Guided** mode and select **Start store shift**. The agent turns a
   low-shelf alert into a 16-unit shelf-move recommendation.
2. Type `Approve the shelf restock`. Maya moves the cases across the playable
   store floor; the shelf rises from 4 to 20 units and the back room falls from
   20 to 4 units. The low-shelf alert closes and a severe-weather alert changes
   the store to its rainy state.
3. Adjust the truck delay, expected demand, and nearby availability. Type
   `Check the weather event` to have the same incident reassessed. Storm demand
   sells 20 cases, leaving the shelf empty and 30 units of demand remaining.
4. Type `Approve this transfer` or `Escalate to regional operations`, then
   watch the Store 205 truck unload 26 cases into the back room. Maya then moves
   20 cases to the aisle, finishing with 20 on the shelf and 10 in the back room.
5. Review the tool calls, turn IDs, business timeline, and session trace below
   the store. Switch to **Live agent** to run the same flow through the Agents API. Live
   mode preserves one session across both turns and links to Platform Logs.

Guided mode makes the demo repeatable and does not call the API. Live mode is
the production-shaped path and may be affected by project rate limits.

## Decisions customers can explore

- **Request store transfer:** choose a long delay, demand above local stock, and
  enough nearby units to cover the gap.
- **Wait for inbound truck:** choose a delay that keeps the truck inside the
  24-hour demand horizon.
- **Needs human review:** choose a long delay and too little nearby inventory to
  cover the projected gap.
