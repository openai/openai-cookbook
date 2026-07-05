#!/usr/bin/env python3
"""Generate or edit AUMARA visual assets from the versioned prompt pack.

Usage:
  python aumara-site/scripts/generate_visual_pack.py --pack concept
  python aumara-site/scripts/generate_visual_pack.py --pack dayparts --quality high

The script writes PNG files and a JSON manifest into
`aumara-site/creative/output_images/`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_FILE = ROOT / "aumara-site" / "creative" / "prompts.json"
OUTPUT_DIR = ROOT / "aumara-site" / "creative" / "output_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AUMARA visual packs with GPT Image")
    parser.add_argument("--pack", default="concept", help="Prompt pack name or 'all'")
    parser.add_argument("--quality", choices=("low", "medium", "high"), default=None)
    parser.add_argument("--size", default=None, help="Override image size for all jobs")
    parser.add_argument("--model", default=None, help="Override the model in prompts.json")
    parser.add_argument("--only", default=None, help="Run only one job ID")
    return parser.parse_args()


def load_config() -> dict[str, Any]:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")
    return json.loads(PROMPT_FILE.read_text(encoding="utf-8"))


def collect_jobs(config: dict[str, Any], pack: str) -> list[dict[str, Any]]:
    packs = config.get("packs", {})
    if pack == "all":
        return [job for jobs in packs.values() for job in jobs]
    if pack not in packs:
        raise ValueError(f"Unknown pack '{pack}'. Available: {', '.join(sorted(packs))}, all")
    return list(packs[pack])


def save_result(result: Any, path: Path) -> None:
    data = result.data[0].b64_json
    if not data:
        raise RuntimeError("Image response did not contain b64_json")
    path.write_bytes(base64.b64decode(data))


def main() -> int:
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 2

    config = load_config()
    jobs = collect_jobs(config, args.pack)
    if args.only:
        jobs = [job for job in jobs if job.get("id") == args.only]
        if not jobs:
            print(f"ERROR: no job with id '{args.only}' in pack '{args.pack}'", file=sys.stderr)
            return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    model = args.model or config.get("model", "gpt-image-2")
    default_quality = args.quality or config.get("default_quality", "medium")
    default_size = args.size or config.get("default_size", "1536x1024")
    manifest: list[dict[str, Any]] = []

    for job in jobs:
        job_id = job["id"]
        mode = job.get("mode", "generate")
        quality = args.quality or job.get("quality", default_quality)
        size = args.size or job.get("size", default_size)
        prompt = job["prompt"]
        out_path = OUTPUT_DIR / f"{job_id}.png"

        print(f"[{mode}] {job_id} · {model} · {quality} · {size}")
        started = datetime.now(timezone.utc)

        if mode == "generate":
            result = client.images.generate(
                model=model,
                prompt=prompt,
                quality=quality,
                size=size,
            )
        elif mode == "edit":
            input_path = ROOT / job["input"]
            if not input_path.exists():
                print(f"SKIP: missing input image {input_path}")
                manifest.append({
                    "id": job_id,
                    "status": "skipped_missing_input",
                    "input": str(input_path.relative_to(ROOT)),
                })
                continue
            with input_path.open("rb") as image_file:
                result = client.images.edit(
                    model=model,
                    image=[image_file],
                    prompt=prompt,
                    quality=quality,
                    size=size,
                )
        else:
            raise ValueError(f"Unsupported mode '{mode}' for {job_id}")

        save_result(result, out_path)
        completed = datetime.now(timezone.utc)
        manifest.append({
            "id": job_id,
            "status": "completed",
            "mode": mode,
            "model": model,
            "quality": quality,
            "size": size,
            "output": str(out_path.relative_to(ROOT)),
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "prompt": prompt,
        })

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
