import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Tuple, Any, List

from openai import OpenAI

# Default task text aligned with the Top-K evaluation used in the notebook
DEFAULT_TASK_TEXT = (
    "Your task:\n"
    "Compute the exact Top-K most frequent tokens from a given text.\n\n"
    "Tokenization:\n"
    "- Case-insensitive tokenization using an ASCII regex; produce lowercase tokens. Lowercasing the entire text is NOT required (per-token lowercasing is acceptable).\n"
    "- Tokens are ASCII [a-z0-9]+ sequences; all other characters are separators (use a regex).\n\n"
    "Inputs:\n"
    "- Two globals are provided: text (string) and k (int). Do not reassign them.\n\n"
    "Requirements:\n"
    "1) Compute Top-K sorted by count desc, then token asc (i.e., sort key = (-count, token)).\n"
    "2) Set top_k to a list of (token, count) tuples, length = min(k, number of unique tokens).\n"
    "3) Handle edge cases: if k <= 0, top_k = [].\n"
    "4) Do not use input(), file I/O, or network access. The script must run as-is with the provided globals.\n\n"
    "Output contract:\n"
    "- At the end of execution, top_k must be defined exactly as described.\n"
    "- Optional: if printing, print only top_k on the last line as a Python literal or JSON.\n\n"
    "Note:\n"
    "- Do not rely on Counter.most_common tie ordering; implement the specified sort.\n"
)


def _load_system_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assemble_messages(system_prompt: str, code: str, task: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "developer",
            "content": [
                {"type": "input_text", "text": system_prompt},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Evaluate the following code output\n\n"
                        "<code_output>\n{code}\n</code_output>\n\n"
                        "on the following task instructions\n<task>\n{task}\n</task>"
                    ).format(code=code, task=task),
                }
            ],
        },
    ]


def _to_text(resp: Any) -> str:
    if getattr(resp, "output_text", None):
        return resp.output_text
    try:
        parts = []
        for item in (getattr(resp, "output", []) or []):
            if getattr(item, "type", None) == "message":
                for seg in (getattr(item, "content", []) or []):
                    if getattr(seg, "type", None) == "output_text":
                        parts.append(getattr(seg, "text", "") or "")
        return "".join(parts) or str(resp)
    except Exception:
        return str(resp)


def _safe_parse_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    # Try direct load
    try:
        return json.loads(text), None
    except Exception as e:
        last_err = str(e)
    # Try to extract the largest JSON object via regex braces matching heuristic
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            return json.loads(candidate), None
    except Exception as e2:
        last_err = str(e2)
    return None, last_err


def judge_folder(
    *,
    results_dir: str,
    out_dir: Optional[str] = None,
    model: str = "gpt-5",
    system_prompt_path: str = "llm_as_judge.txt",
    task_text: Optional[str] = None,
    concurrency: int = 5,
    max_retries: int = 3,
    backoff: float = 1.0,
) -> Path:
    """
    Evaluate each .py code file in results_dir with an LLM-as-judge and write per-file JSON judgments.
    Returns the output directory path.
    """
    in_dir = Path(results_dir)
    assert in_dir.exists(), f"Results folder not found: {in_dir}"

    # Output directory
    if out_dir is None:
        name = in_dir.name.lower()
        if "baseline" in name:
            suffix = "baseline"
        elif "optimized" in name:
            suffix = "optimized"
        else:
            suffix = "baseline"
        out_dir = in_dir.parent / f"results_llm_as_judge_{suffix}"
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Load prompts
    system_prompt = _load_system_prompt(Path(system_prompt_path))
    task = task_text or DEFAULT_TASK_TEXT

    client = OpenAI()

    def run_one(py_path: Path) -> Tuple[str, dict]:
        code = py_path.read_text(encoding="utf-8", errors="ignore")
        messages = _assemble_messages(system_prompt, code, task)

        for attempt in range(max_retries):
            try:
                resp = client.responses.create(
                    model=model,
                    input=messages,
                    text={"format": {"type": "text"}, "verbosity": "medium"},
                    reasoning={"effort": "medium", "summary": "auto"},
                    tools=[],
                )
                raw = _to_text(resp)
                parsed, err = _safe_parse_json(raw)
                result = {
                    "file": str(py_path.name),
                    "raw": raw,
                    "parsed": parsed,
                    "parse_error": err,
                }
                return py_path.name, result
            except Exception as e:
                if attempt == max_retries - 1:
                    return py_path.name, {
                        "file": str(py_path.name),
                        "error": f"Request failed: {e}",
                    }
                time.sleep(backoff * (2 ** attempt))
        # Should not reach
        return py_path.name, {"file": str(py_path.name), "error": "Exhausted retries"}

    py_files = sorted([p for p in in_dir.glob("*.py")])

    results: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(run_one, p): p.name for p in py_files}
        for fut in as_completed(futures):
            fname, res = fut.result()
            results[fname] = res
            # write per-file json immediately
            out_file = out_path / f"{Path(fname).stem}.json"
            out_file.write_text(json.dumps(res, indent=2), encoding="utf-8")

    # Build a summary CSV with scores if parseable
    import csv as _csv

    summary_csv = out_path / "judgement_summary.csv"
    with open(summary_csv, "w", newline="") as fp:
        writer = _csv.writer(fp)
        writer.writerow(["File", "adherence_score", "code_quality_score", "parse_error", "error"])
        for fname in sorted(results.keys()):
            r = results[fname]
            adher = None
            codeq = None
            perr = r.get("parse_error")
            err = r.get("error")
            parsed = r.get("parsed")
            if isinstance(parsed, dict):
                fj = parsed.get("final_judgement") or {}
                adher = fj.get("adherence_score")
                codeq = fj.get("code_quality_score")
            writer.writerow([fname, adher, codeq, perr or "", err or ""])

    return out_path


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Run LLM-as-judge over generated scripts.")
    ap.add_argument("--optimized_dir", default="results_topk_optimized")
    ap.add_argument("--baseline_dir", default="results_topk_baseline")
    ap.add_argument("--system_prompt", default="llm_as_judge.txt")
    ap.add_argument("--model", default="gpt-5")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--task_file", default=None, help="Optional path to a file containing task instructions")
    ap.add_argument("--out_dir_baseline", default=None, help="Write judgments for baseline run to this directory (used as-is)")
    ap.add_argument("--out_dir_optimized", default=None, help="Write judgments for optimized run to this directory (used as-is)")

    args = ap.parse_args()

    task_text = None
    if args.task_file:
        task_text = Path(args.task_file).read_text(encoding="utf-8")

    # Baseline
    judge_folder(
        results_dir=args.baseline_dir,
        out_dir=args.out_dir_baseline,  # used as-is if provided
        model=args.model,
        system_prompt_path=args.system_prompt,
        task_text=task_text,
        concurrency=args.concurrency,
    )
    # Optimized
    judge_folder(
        results_dir=args.optimized_dir,
        out_dir=args.out_dir_optimized,  # used as-is if provided
        model=args.model,
        system_prompt_path=args.system_prompt,
        task_text=task_text,
        concurrency=args.concurrency,
    )


# --- Ad-hoc helpers for single-file judging and summary rebuild ---
def judge_one(
    *,
    py_path: str,
    out_dir: Optional[str] = None,
    model: str = "gpt-5",
    system_prompt_path: str = "llm_as_judge.txt",
    task_text: Optional[str] = None,
    max_retries: int = 3,
    backoff: float = 1.0,
) -> Path:
    """Judge a single Python file and write its JSON to the appropriate output directory.

    Returns the path to the written JSON.
    """
    in_path = Path(py_path)
    assert in_path.exists(), f"Python file not found: {in_path}"

    # Resolve output directory
    if out_dir is None:
        parent = in_path.parent.name.lower()
        if "baseline" in parent:
            suffix = "baseline"
        elif "optimized" in parent:
            suffix = "optimized"
        else:
            suffix = "baseline"
        out_dir = in_path.parent.parent / f"results_llm_as_judge_{suffix}"
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Load prompts
    system_prompt = _load_system_prompt(Path(system_prompt_path))
    task = task_text or DEFAULT_TASK_TEXT

    # Read code and call model
    code = in_path.read_text(encoding="utf-8", errors="ignore")
    messages = _assemble_messages(system_prompt, code, task)

    client = OpenAI()
    last_err: Optional[str] = None
    for attempt in range(max_retries):
        try:
            resp = client.responses.create(
                model=model,
                input=messages,
                text={"format": {"type": "text"}, "verbosity": "medium"},
                reasoning={"effort": "medium", "summary": "auto"},
                tools=[],
            )
            raw = _to_text(resp)
            parsed, err = _safe_parse_json(raw)
            result = {
                "file": str(in_path.name),
                "raw": raw,
                "parsed": parsed,
                "parse_error": err,
            }
            out_json = out_path / f"{in_path.stem}.json"
            out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return out_json
        except Exception as e:
            last_err = str(e)
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))

    raise RuntimeError(f"Failed to judge {in_path}: {last_err}")


def rebuild_summary(*, out_dir: str) -> Path:
    """Rebuild judgement_summary.csv from all JSON files present in out_dir and return its path."""
    base = Path(out_dir)
    results: Dict[str, dict] = {}
    for p in sorted(base.glob("*.json")):
        try:
            results[p.name] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

    import csv as _csv
    summary_csv = base / "judgement_summary.csv"
    with open(summary_csv, "w", newline="") as fp:
        writer = _csv.writer(fp)
        writer.writerow(["File", "adherence_score", "code_quality_score", "parse_error", "error"])
        for fname in sorted(results.keys()):
            r = results[fname]
            adher = None
            codeq = None
            perr = (r.get("parse_error") if isinstance(r, dict) else None)
            err = (r.get("error") if isinstance(r, dict) else None)
            parsed = r.get("parsed") if isinstance(r, dict) else None
            if isinstance(parsed, dict):
                fj = parsed.get("final_judgement") or {}
                adher = fj.get("adherence_score")
                codeq = fj.get("code_quality_score")
            writer.writerow([r.get("file") or fname, adher, codeq, perr or "", err or ""]) 

    return summary_csv
