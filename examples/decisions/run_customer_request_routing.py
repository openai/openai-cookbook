"""Execute the companion notebook without Jupyter; offline unless --live is set."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live", action="store_true",
        help="Download public data and make 120 billable Decisions requests; requires OPENAI_API_KEY.",
    )
    mode.add_argument(
        "--preview", action="store_true",
        help="Make one billable Decisions request and print its request and response; requires OPENAI_API_KEY.",
    )
    args = parser.parse_args()
    os.environ["RUN_DECISIONS_API"] = "1" if args.live or args.preview else "0"
    path = Path(__file__).with_name("customer_request_routing.ipynb")
    notebook = json.loads(path.read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__"}
    if args.preview:
        # Load imports/configuration and the request functions without loading data.
        for index in (2, 6):
            source = notebook["cells"][index]["source"]
            source = source if isinstance(source, str) else "".join(source)
            exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)
        message = "My new card has not arrived. Can you help me track its delivery?"
        print("ONE-REQUEST LIVE PREVIEW: demonstration input, not evaluation evidence")
        print("POST", namespace["API_URL"])
        print(json.dumps({"model": namespace["MODEL"], "input": message,
                          "questions": [namespace["QUESTION"]]}, indent=2))
        response, latency_ms = namespace["request_prediction"](message)
        print("LIVE API RESPONSE")
        print(json.dumps(response, indent=2))
        route, confidence = namespace["parse_prediction"](response)
        print(json.dumps({"route": route, "confidence": confidence,
                          "latency_ms": latency_ms}, indent=2))
        return
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            source = cell["source"]
            source = source if isinstance(source, str) else "".join(source)
            exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)


if __name__ == "__main__":
    main()
