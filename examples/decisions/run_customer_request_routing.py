"""Execute the companion notebook without Jupyter; offline unless --live is set."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true",
        help="Download public data and make 120 billable Decisions requests; requires OPENAI_API_KEY.",
    )
    args = parser.parse_args()
    os.environ["RUN_DECISIONS_API"] = "1" if args.live else "0"
    path = Path(__file__).with_name("customer_request_routing.ipynb")
    notebook = json.loads(path.read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__"}
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            source = cell["source"]
            source = source if isinstance(source, str) else "".join(source)
            exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)


if __name__ == "__main__":
    main()
