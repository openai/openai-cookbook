import os
import io
import re
import csv
import json
import ast
import time
import tracemalloc
import runpy
from pathlib import Path
from contextlib import redirect_stdout
from collections import Counter
from typing import Optional

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Disallowed usage (static scan)
DISALLOWED_IMPORTS = {
    "sqlite3": "external_storage",
    "tempfile": "external_storage",
    "shelve": "external_storage",
    "requests": "network",
    "urllib": "network",
    "http": "network",
    "socket": "network",
}
DISALLOWED_PATTERNS = [
    ("file_io", re.compile(r"(?<![\w\.])open\(")),
]


def evaluate_folder(
    folder_path: str,
    k: int = 500,
    scale_tokens: int = 5_000_000,
    csv_path: Optional[str] = None,
) -> dict:
    # === Build deterministic, more intense dataset with many ties near Top-K ===
    import random

    random.seed(1337)
    vocab_top = [f"w{i:04d}" for i in range(1, 401)]
    vocab_tail = [f"w{i:04d}" for i in range(401, 5001)]

    counts_plan = {}

    # Head: decreasing counts
    for i, tok in enumerate(vocab_top[:150], start=1):
        c = max(1200, int(5000 / (i ** 0.5)))
        counts_plan[tok] = c

    # Plateau: create many equal-count tokens to stress tie-breaking near K
    plateau_tokens = vocab_top[150:350]  # 200 tokens
    for tok in plateau_tokens:
        counts_plan[tok] = 1000

    # Remainder of top block
    for tok in vocab_top[350:400]:
        counts_plan[tok] = 900

    # Materialize text via generator to avoid a huge list
    residual = max(0, scale_tokens - sum(counts_plan.values()))
    tail_vocab = vocab_tail

    def iter_tokens():
        for tok, c in counts_plan.items():
            for _ in range(c):
                yield tok
        for i in range(residual):
            yield tail_vocab[i % len(tail_vocab)]

    test_text = " ".join(iter_tokens())

    # === Ground truth (from construction plan) ===
    counts = Counter()
    counts.update(counts_plan)
    for i in range(residual):
        counts[tail_vocab[i % len(tail_vocab)]] += 1

    def topk_from_counts(cnt: Counter, k: int):
        items = list(cnt.items())
        items.sort(key=lambda x: (-x[1], x[0]))
        return items[:k]

    ground_truth = topk_from_counts(counts, k)

    # === Helpers ===
    def coerce_topk(obj):
        if isinstance(obj, list):
            out = []
            for it in obj:
                if isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[0], str) and isinstance(it[1], (int, float)):
                    out.append((it[0], int(it[1])))
                else:
                    return None
            return out
        return None

    def parse_topk_from_stdout(stdout_str):
        lines = [ln.strip() for ln in stdout_str.strip().splitlines() if ln.strip()]
        for candidate in reversed(lines):
            try:
                val = ast.literal_eval(candidate)
                coerced = coerce_topk(val)
                if coerced is not None:
                    return coerced
            except Exception:
                pass
        return None

    def is_sorted_topk(pairs):
        return all((pairs[i][1] > pairs[i+1][1]) or (pairs[i][1] == pairs[i+1][1] and pairs[i][0] <= pairs[i+1][0]) for i in range(len(pairs)-1))

    def precision_at_k(pred, truth):
        pred_tokens = {t for t, _ in (pred[:k] if isinstance(pred, list) else [])}
        truth_tokens = {t for t, _ in truth[:k]}
        if not pred_tokens:
            return 0.0
        return len(pred_tokens & truth_tokens) / min(len(pred_tokens), k)

    def scan_constraints(src: str) -> Optional[str]:
        # Imports
        for name, tag in DISALLOWED_IMPORTS.items():
            # simple import detection
            if re.search(rf"\bimport\s+{re.escape(name)}\b|\bfrom\s+{re.escape(name)}\b", src):
                return f"Constraint violation: disallowed import '{name}' ({tag})"
        # Patterns
        for tag, rx in DISALLOWED_PATTERNS:
            if rx.search(src):
                return f"Constraint violation: disallowed pattern '{tag}'"
        return None

    # === Warm-up (optional) ===
    py_files = sorted([f for f in os.listdir(folder_path) if f.endswith(".py")])
    if py_files:
        warmup_path = os.path.join(folder_path, py_files[0])
        try:
            _ = runpy.run_path(warmup_path, run_name="__main__", init_globals={"text": test_text, "k": k})
            tracemalloc.start()
            _ = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        except Exception:
            pass

    # === Evaluation ===
    rows = []
    compile_success_count = 0
    total_time = 0.0
    total_mem = 0
    exact_count = 0
    sorted_ok_count = 0
    violation_count = 0

    for file_name in py_files:
        file_path = os.path.join(folder_path, file_name)

        # Static constraint scan
        violation = None
        try:
            src_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            violation = scan_constraints(src_text)
        except Exception:
            pass

        if violation:
            violation_count += 1
            rows.append([file_name, False, "", "", "", ground_truth[:5], violation, "", "", violation])
            continue

        f = io.StringIO()
        tracemalloc.start()
        start = time.perf_counter()
        peak_mem = None
        result = None

        try:
            with redirect_stdout(f):
                namespace = runpy.run_path(file_path, run_name="__main__", init_globals={"text": test_text, "k": k})
            elapsed = time.perf_counter() - start
            _, peak_mem = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            compile_success_count += 1

            stdout_str = f.getvalue()
            # prefer namespace variable
            if "top_k" in namespace:
                result = coerce_topk(namespace["top_k"])
            if result is None:
                result = parse_topk_from_stdout(stdout_str)

            total_time += elapsed
            total_mem += (peak_mem or 0)

            is_exact = (result == ground_truth)
            if is_exact:
                exact_count += 1

            is_sorted_ok = bool(result) and is_sorted_topk(result)
            if is_sorted_ok:
                sorted_ok_count += 1

            p_at_k = precision_at_k(result or [], ground_truth)

            rows.append([
                file_name,
                True,
                elapsed,
                peak_mem,
                (result[:5] if isinstance(result, list) else ""),
                (ground_truth[:5]),
                is_exact,
                is_sorted_ok,
                f"{p_at_k:.3f}",
                "",
            ])

        except Exception as e:
            try:
                tracemalloc.stop()
            except Exception:
                pass
            rows.append([file_name, False, "", "", "", ground_truth[:5], f"Runtime/Import Error: {e}", "", "", ""])

    # === Write CSV (allow caller to pass a directory or explicit file) ===
    base_dir = Path(folder_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    name = base_dir.name.lower()
    if "baseline" in name:
        default_name = "run_results_topk_baseline.csv"
    elif "optimized" in name:
        default_name = "run_results_topk_optimized.csv"
    else:
        default_name = "run_results_topk.csv"

    # If csv_path is provided:
    # - If it's absolute, use it as-is
    # - If it's relative, resolve it under folder_path (base_dir) so results live with the evaluated runs
    # - If it's a directory, place the default file name inside it
    if csv_path:
        csv_path_obj = Path(csv_path)
        if not csv_path_obj.is_absolute():
            csv_path_obj = (base_dir / csv_path_obj)
        if csv_path_obj.suffix.lower() != ".csv":
            csv_path_obj = csv_path_obj / default_name
        csv_path_obj.parent.mkdir(parents=True, exist_ok=True)
    else:
        csv_path_obj = base_dir / default_name

    with open(csv_path_obj, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "File Name",
            "Compiled",
            "Execution Time (s)",
            "Peak Memory (bytes)",
            "Reported Top-K (first 5)",
            "Ground Truth (first 5)",
            "Exact Match",
            "Sorted Correctly",
            "Precision@K",
            "Violation",
        ])
        writer.writerows(rows)

    # === Summary files (inside same folder) ===
    total_runs = len(py_files)
    avg_time = (total_time / compile_success_count) if compile_success_count else None
    avg_peak_kb = (total_mem / compile_success_count / 1024) if compile_success_count else None
    summary = {
        "total_runs": total_runs,
        "successes": compile_success_count,
        "avg_exec_time_s": avg_time,
        "avg_peak_mem_kb": avg_peak_kb,
        "exact_matches": exact_count,
        "sorted_correctly": sorted_ok_count,
        "violations": violation_count,
        "csv": str(csv_path_obj),
        "folder": str(base_dir),
        "k": k,
        "scale_tokens": scale_tokens,
    }
    summary_json = csv_path_obj.with_name(csv_path_obj.stem + "_summary.json")
    summary_txt = csv_path_obj.with_name(csv_path_obj.stem + "_summary.txt")
    with open(summary_json, "w") as fp:
        json.dump(summary, fp, indent=2)
    with open(summary_txt, "w") as fp:
        fp.write("===== SUMMARY =====\n")
        fp.write(f"Total evaluated runs: {total_runs}\n")
        fp.write(f"Compilation/Execution Success: {compile_success_count}/{total_runs} ({(compile_success_count/total_runs)*100:.2f}%)\n")
        fp.write(f"Violations (static scan): {violation_count}\n")
        if compile_success_count > 0:
            fp.write(f"Average Execution Time (successful): {avg_time:.6f} s\n")
            fp.write(f"Average Peak Memory (successful): {avg_peak_kb:.2f} KB\n")
            fp.write(f"Exact matches: {exact_count}/{compile_success_count}\n")
            fp.write(f"Sorted correctly: {sorted_ok_count}/{compile_success_count}\n")
        fp.write(f"CSV written to: {csv_path_obj}\n")

    print("===== SUMMARY =====")
    print(f"Total evaluated runs: {total_runs}")
    print(f"Compilation/Execution Success: {compile_success_count}/{total_runs} ({(compile_success_count/total_runs)*100:.2f}%)")
    print(f"Violations (static scan): {violation_count}")
    if compile_success_count > 0:
        print(f"Average Execution Time (successful): {avg_time:.6f} s")
        print(f"Average Peak Memory (successful): {avg_peak_kb:.2f} KB")
        print(f"Exact matches: {exact_count}/{compile_success_count}")
        print(f"Sorted correctly: {sorted_ok_count}/{compile_success_count}")
    print(f"\nCSV written to: {csv_path_obj}")
    print(f"Summary JSON written to: {summary_json}")
    print(f"Summary TXT written to: {summary_txt}")

    return summary
