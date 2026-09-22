# Pay a 402-priced API in Nano (XNO) from an OpenAI agent

An agent that calls a paid endpoint often pays per call. The existing cookbook
example in this directory (`.../agentcore_payments`) settles those calls in
**USDC on an EVM testnet**. This example adds a second, feeless rail: Nano
(XNO), a self-custodied network where a transfer costs nothing and settles on
ledger in under a second — no gas, no account, no issuer.

It reuses the MIT-licensed `feeless402` library (PyPI, import name `nano_pay`),
which implements the standard x402 handshake: parse the server's `402` quote,
enforce a price cap, sign locally, retry with the payment header, and verify
settlement on the ledger. No Nano payment logic is rebuilt here.

## What's in the tool

`make_nano_x402_tool()` returns a regular function tool. The wallet and RPC are
constructed once at tool creation from the environment and **never handed to
the model**; the spend cap (`X402_MAX_XNO`, default `0.01` XNO) is enforced
inside `request_with_payment`.

```python
agent = Agent(
    name="Nano buyer",
    instructions="Given a 402-priced URL, pay it with the nano tool and report the data.",
    tools=[make_nano_x402_tool()],
)
```

## Run

```bash
pip install openai-agents feeless402
export OPENAI_API_KEY=...
export X402_WALLET_PATH=/path/to/wallet.json   # optional; see feeless402 docs
export X402_MAX_XNO=0.01                        # optional spend cap (XNO)
python pay_nano_x402.py
```

Point the agent at any live endpoint that returns `402 Payment Required` with
a `nano:mainnet` accept.

## Verify offline (no wallet, no funds)

```bash
python pay_nano_x402.py --self-test
```

The self-test spins up a stdlib-only Nano-only `402` seller and drives it
through the **real** `nano_pay.x402` client — `parse_quote` → `collect_offers`
selects the `nano:mainnet`/XNO accept, and `request_with_payment(..., dry_run=True)`
completes the two-phase handshake. Output `SELF_TEST_OK`, exit 0. This verifies
the flow without moving funds, consistent with how the AgentCore example checks
its testnet path.
