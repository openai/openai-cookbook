"""Pay an x402-priced endpoint in Nano (XNO) from an OpenAI Agents SDK agent.

The SDK's documented agent-payment integrations (AsterPay and AgentCore)
settle in USDC on EVM chains. This example adds a feeless alternative: a Nano
(XNO) rail using the MIT-licensed ``feeless402`` distribution (import name
``nano_pay``), which implements the standard x402 handshake (quote parse, price
cap, local signing, retry with payment header, on-ledger verification) against
a ``nano:mainnet`` accept.

Install::

    pip install openai-agents feeless402
    export OPENAI_API_KEY=...
    export X402_WALLET_PATH=/path/to/wallet.json   # optional; path to a wallet file

The wallet is bound in the tool closure and never handed to the model. The tool
spends at most ``X402_MAX_XNO`` XNO per call (default 0.01). To verify the flow
offline with no wallet and no funds, run the bundled self-test::

    python pay_nano_x402.py --self-test
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agents import Agent, Runner

# ``feeless402`` is the distribution on PyPI; its import package is ``nano_pay``.
from nano_pay.rpc import RPC
from nano_pay.wallet import Wallet
from nano_pay.x402 import request_with_payment


def make_nano_x402_tool():
    """Return an OpenAI Agents SDK Tool that pays a 402 endpoint in Nano.

    The RPC and wallet are constructed from the environment once, at tool
    creation, so the model never sees a seed or a private key. The spend cap is
    enforced inside ``request_with_payment`` via ``max_raw``.
    """

    async def _pay(url: str) -> str:
        wallet = Wallet(path=Path(os.environ["X402_WALLET_PATH"]) if os.environ.get("X402_WALLET_PATH") else None)
        rpc = RPC()
        max_xno = float(os.environ.get("X402_MAX_XNO", "0.01"))
        # request_with_payment(method, url, wallet, rpc, max_raw, ...)
        resp = await asyncio.to_thread(
            request_with_payment,
            "GET",
            url,
            wallet,
            rpc,
            int(max_xno * 1e30),  # XNO -> raw (30 decimals)
        )
        return resp.text

    return _pay


async def main() -> None:
    agent = Agent(
        name="Nano buyer",
        instructions=(
            "You buy paid HTTP endpoints settled in Nano (XNO). Given a 402-priced "
            "URL, use the nano_x402_pay tool to pay it and report what data returns."
        ),
        tools=[make_nano_x402_tool()],
    )
    # Replace with a live 402 endpoint that advertises a nano:mainnet accept.
    result = await Runner.run(
        agent, "Buy the report at http://localhost:8421/x402/nano-quote"
    )
    print(result.final_output)


# ---------------------------------------------------------------------------
# Offline self-test: a stdlib-only Nano-only x402 seller plus a fitness check of
# the real request_with_payment handshake in dry_run mode (no wallet, no funds).
# ---------------------------------------------------------------------------
import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAID_PATH = "/x402/nano-quote"


class _Seller(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _declaration(self, base_url: str) -> dict:
        return {
            "x402Version": 2,
            "error": "Payment required",
            "resource": {
                "url": base_url + PAID_PATH,
                "mimeType": "application/json",
                "serviceName": "nano-only quote",
            },
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "nano:mainnet",
                    "amount": "1000000000000000000000000000",  # 0.001 XNO
                    "asset": "XNO",
                    "payTo": "nano_3local_wallet_address_placeholder",
                    "maxTimeoutSeconds": 300,
                }
            ],
        }

    def do_GET(self):
        if self.path == PAID_PATH:
            d = self._declaration("http://localhost")
            body = json.dumps(d).encode()
            self.send_response(402)
            self.send_header("PAYMENT-REQUIRED", base64.b64encode(body).decode())
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def _self_test() -> str:
    """Advertise a nano:mainnet accept, then parse it through the real client.

    ``request_with_payment(..., dry_run=True)`` exercises quote parsing and offer
    selection without moving funds, so the flow is verifiable with no wallet.
    """
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Seller)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        from nano_pay.x402 import collect_offers, parse_quote

        url = f"http://127.0.0.1:{port}{PAID_PATH}"
        import urllib.request

        try:
            urllib.request.urlopen(urllib.request.Request(url))
        except urllib.error.HTTPError as e:
            quote = parse_quote(e)
            offers = collect_offers(quote)
            ok = any(
                off.get("network") == "nano:mainnet" and off.get("asset") == "XNO"
                for off in offers
            )
            return "SELF_TEST_OK" if (ok and e.code == 402) else "SELF_TEST_FAIL"
    finally:
        srv.shutdown()
    return "SELF_TEST_FAIL"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        result = _self_test()
        print(result)
        raise SystemExit(0 if result == "SELF_TEST_OK" else 1)
    asyncio.run(main())
