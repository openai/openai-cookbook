import re
import time
import random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from openai import OpenAI

CODE_BLOCK = re.compile(r"```[ \t]*(?:[A-Za-z0-9_+\-]+)?[ \t]*\r?\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    # Prefer the largest fenced code block if present
    blocks = CODE_BLOCK.findall(text)
    if blocks:
        return max(blocks, key=len).strip()
    # Fallback: strip a single leading/trailing fence if present
    stripped = re.sub(r"^\s*```[^\n]*\r?\n", "", text)
    stripped = re.sub(r"\n```[ \t]*$", "", stripped)
    return stripped.strip()


def _call_model_with_retry(
    *, model: str, dev_prompt: str, user_prompt: str, max_retries: int = 3, backoff: float = 1.0
) -> str:
    client = OpenAI()
    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": dev_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "text": {"format": {"type": "text"}, "verbosity": "medium"},
        "reasoning": {"effort": "medium", "summary": "auto"},
        "tools": [],
    }
    for attempt in range(max_retries):
        try:
            resp = client.responses.create(**payload)
            return getattr(resp, "output_text", str(resp))
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt) + random.random() * 0.25)


def generate_baseline_topk(
    *,
    model: str = "gpt-5",
    n_runs: int = 30,
    concurrency: int = 10,
    output_dir: str = "results_topk_baseline",
    dev_prompt: str,
    user_prompt: str,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def run_one(i: int):
        text = _call_model_with_retry(model=model, dev_prompt=dev_prompt, user_prompt=user_prompt)
        code = extract_code(text)
        return i, code

    written = 0
    futures = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for i in range(1, n_runs + 1):
            futures.append(pool.submit(run_one, i))
        for fut in as_completed(futures):
            i, code = fut.result()
            out_path = out / f"run_{i:02d}.py"
            out_path.write_text(code, encoding="utf-8")
            written += 1
            print(f"[{written}/{n_runs}] Wrote {out_path} — remaining: {n_runs - written}")
    print(f"Done. Saved {n_runs} files to: {out.resolve()}")
    return out


