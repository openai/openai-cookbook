# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "openai>=3.13.0",
#     "docker",
#     "python-dotenv",
# ]
# ///

"""Review a mounted document folder and print the resulting artifacts."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Support direct execution from any working directory.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


from examples.agents_api.apps.document_review.agent import review_documents

EXAMPLE_DIR = Path(__file__).resolve().parent


async def run_batch(input_directory: Path, output_directory: Path) -> None:
    batch = await review_documents(input_directory, output_directory)
    print(batch["summary"])
    print(f"\nPolicy applied: {batch['reviews'][0]['report']['policy_id']}")
    print(f"Documents reviewed: {len(batch['reviews'])}")
    print(f"Subagents created: {batch['subagents']}")
    print(f"Artifacts: {output_directory.resolve()}")
    for review in batch["reviews"]:
        print(f"  - {review['document']}: {Path(review['document']).stem}.json")
    print("  - summary.json")
    print("  - review-activity.json (retained commands and turn IDs)")
    print("\nStatus: awaiting human approval")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review document batches in an isolated sandbox."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        metavar="DIRECTORY",
        help="Documents to review.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("review-output"),
        help="Output artifact directory.",
    )
    args = parser.parse_args()
    load_dotenv(EXAMPLE_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run_batch(args.input, args.output))


if __name__ == "__main__":
    main()
