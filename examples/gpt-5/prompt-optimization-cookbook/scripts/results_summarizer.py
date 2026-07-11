from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Minimal typing-friendly containers
@dataclass
class QuantRow:
    file: str
    compiled: bool
    exec_time_s: Optional[float]
    peak_mem_bytes: Optional[int]
    exact: Optional[bool]
    sorted_ok: Optional[bool]
    violation: Optional[str]

@dataclass
class JudgeRow:
    file: str
    adherence_score: Optional[float]
    code_quality_score: Optional[float]
    parse_error: Optional[str]
    error: Optional[str]

@dataclass
class GroupSummary:
    name: str
    n_total: int
    n_success: int
    n_violations: int
    exact_rate: float
    sorted_rate: float
    avg_time_s: Optional[float]
    avg_peak_kb: Optional[float]
    avg_adherence: Optional[float]
    avg_code_quality: Optional[float]


def _read_quant_csv(path: Path) -> List[QuantRow]:
    rows: List[QuantRow] = []
    with open(path, newline="") as fp:
        r = csv.DictReader(fp)
        for d in r:
            compiled = str(d.get("Compiled", "")).strip().lower() == "true"
            def _float(x):
                try:
                    return float(x)
                except Exception:
                    return None
            def _int(x):
                try:
                    return int(x)
                except Exception:
                    return None
            def _bool(x):
                sx = str(x).strip().lower()
                if sx in ("true", "false"):
                    return sx == "true"
                return None
            rows.append(
                QuantRow(
                    file=str(d.get("File Name", "")),
                    compiled=compiled,
                    exec_time_s=_float(d.get("Execution Time (s)", "")),
                    peak_mem_bytes=_int(d.get("Peak Memory (bytes)", "")),
                    exact=_bool(d.get("Exact Match", "")),
                    sorted_ok=_bool(d.get("Sorted Correctly", "")),
                    violation=(d.get("Violation") if "Violation" in d else None),
                )
            )
    return rows


def _read_judge_csv(path: Path) -> List[JudgeRow]:
    out: List[JudgeRow] = []
    with open(path, newline="") as fp:
        r = csv.DictReader(fp)
        for d in r:
            def _num(x):
                try:
                    return float(x)
                except Exception:
                    return None
            out.append(
                JudgeRow(
                    file=str(d.get("File", "")),
                    adherence_score=_num(d.get("adherence_score")),
                    code_quality_score=_num(d.get("code_quality_score")),
                    parse_error=d.get("parse_error"),
                    error=d.get("error"),
                )
            )
    return out


def _avg(nums: List[float]) -> Optional[float]:
    nums2 = [x for x in nums if x is not None]
    if not nums2:
        return None
    return sum(nums2) / len(nums2)


def summarize_groups(
    *,
    quant_paths: Dict[str, Path],
    judge_paths: Dict[str, Path],
) -> Dict[str, GroupSummary]:
    summaries: Dict[str, GroupSummary] = {}
    for name, qpath in quant_paths.items():
        qrows = _read_quant_csv(qpath)
        jrows = _read_judge_csv(judge_paths[name]) if name in judge_paths and judge_paths[name].exists() else []
        jmap = {Path(j.file).stem: j for j in jrows}

        n_total = len(qrows)
        n_success = sum(1 for r in qrows if r.compiled)
        n_viol = sum(1 for r in qrows if (r.violation or "").strip())
        exact_rate = (
            sum(1 for r in qrows if r.exact) / n_success if n_success else 0.0
        )
        sorted_rate = (
            sum(1 for r in qrows if r.sorted_ok) / n_success if n_success else 0.0
        )
        avg_time_s = _avg([r.exec_time_s for r in qrows if r.compiled and r.exec_time_s is not None])
        avg_peak_kb = _avg([
            (r.peak_mem_bytes or 0) / 1024.0 for r in qrows if r.compiled and r.peak_mem_bytes is not None
        ])

        # Judge averages
        avg_adherence = _avg([jr.adherence_score for jr in jrows if jr.adherence_score is not None])
        avg_codeq = _avg([jr.code_quality_score for jr in jrows if jr.code_quality_score is not None])

        summaries[name] = GroupSummary(
            name=name,
            n_total=n_total,
            n_success=n_success,
            n_violations=n_viol,
            exact_rate=exact_rate,
            sorted_rate=sorted_rate,
            avg_time_s=avg_time_s,
            avg_peak_kb=avg_peak_kb,
            avg_adherence=avg_adherence,
            avg_code_quality=avg_codeq,
        )
    return summaries


def render_charts(
    *,
    quant_baseline: Path = Path("results_topk_baseline") / "run_results_topk_baseline.csv",
    quant_optimized: Path = Path("results_topk_optimized") / "run_results_topk_optimized.csv",
    judge_baseline: Path = Path("results_llm_as_judge_baseline") / "judgement_summary.csv",
    judge_optimized: Path = Path("results_llm_as_judge_optimized") / "judgement_summary.csv",
    auto_display: bool = False,
    close_after: bool = False,
):
    import matplotlib.pyplot as plt
    # seaborn optional
    try:
        import seaborn as sns  # type: ignore
        sns.set_theme(style="whitegrid")
    except Exception:
        pass

    quant_paths = {
        "baseline": Path(quant_baseline),
        "optimized": Path(quant_optimized),
    }
    judge_paths = {
        "baseline": Path(judge_baseline),
        "optimized": Path(judge_optimized),
    }
    summaries = summarize_groups(quant_paths=quant_paths, judge_paths=judge_paths)

    # Build figure with subplots
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    labels = ["baseline", "optimized"]

    # Helper to fetch values in label order
    def vals(key: str) -> List[float]:
        out: List[float] = []
        for l in labels:
            v = getattr(summaries[l], key)
            out.append(v if v is not None else 0.0)
        return out

    # 1) Avg exec time
    ax = axes[0, 0]
    ax.bar(labels, vals("avg_time_s"), color=["#cbd5e1", "#60a5fa"])  # slate-200, blue-400
    ax.set_title("Average Execution Time (s)")

    # 2) Avg peak memory
    ax = axes[0, 1]
    ax.bar(labels, vals("avg_peak_kb"), color=["#cbd5e1", "#60a5fa"])
    ax.set_title("Average Peak Memory (KB)")

    # 3) Success & Violation stacked bars
    ax = axes[0, 2]
    succ = [summaries[l].n_success for l in labels]
    viol = [summaries[l].n_violations for l in labels]
    total = [summaries[l].n_total for l in labels]
    fail = [total[i] - succ[i] - viol[i] for i in range(len(labels))]
    ax.bar(labels, succ, label="Success", color="#22c55e")
    ax.bar(labels, viol, bottom=succ, label="Violation", color="#f59e0b")
    ax.bar(labels, fail, bottom=[succ[i] + viol[i] for i in range(len(labels))], label="Fail", color="#ef4444")
    ax.set_title("Outcome Breakdown")
    ax.legend()

    # 4) Exact rate
    ax = axes[1, 0]
    ax.bar(labels, [summaries[l].exact_rate * 100 for l in labels], color=["#cbd5e1", "#60a5fa"])
    ax.set_title("Exact Match Rate (%)")

    # 5) Sorted correct rate
    ax = axes[1, 1]
    ax.bar(labels, [summaries[l].sorted_rate * 100 for l in labels], color=["#cbd5e1", "#60a5fa"])
    ax.set_title("Sorted Correctly Rate (%)")

    # 6) LLM scores (adherence vs code quality)
    ax = axes[1, 2]
    x = range(len(labels))
    width = 0.35
    adher = vals("avg_adherence")
    codeq = vals("avg_code_quality")
    ax.bar([i - width / 2 for i in x], adher, width=width, label="Adherence", color="#0ea5e9")
    ax.bar([i + width / 2 for i in x], codeq, width=width, label="Code Quality", color="#8b5cf6")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title("LLM-as-Judge Scores")
    ax.legend()

    fig.tight_layout()

    # Optional in-function display for notebook convenience
    if auto_display:
        try:
            from IPython.display import display  # type: ignore
            display(fig)
        except Exception:
            pass
        if close_after:
            try:
                plt.close(fig)
            except Exception:
                pass

    return fig, summaries


def print_text_summaries(summaries: Dict[str, GroupSummary]):
    for k in ("baseline", "optimized"):
        s = summaries.get(k)
        if not s:
            continue
        print(f"\n=== {k.upper()} ===")
        print(f"Total: {s.n_total}, Success: {s.n_success}, Violations: {s.n_violations}")
        if s.avg_time_s is not None:
            print(f"Avg Time: {s.avg_time_s:.3f}s")
        if s.avg_peak_kb is not None:
            print(f"Avg Peak Memory: {s.avg_peak_kb:.1f} KB")
        print(f"Exact Rate: {s.exact_rate*100:.1f}% | Sorted Rate: {s.sorted_rate*100:.1f}%")
        if s.avg_adherence is not None or s.avg_code_quality is not None:
            print(
                f"LLM Scores — Adherence: {s.avg_adherence or 'NA'}, Code Quality: {s.avg_code_quality or 'NA'}"
            )


if __name__ == "__main__":
    import argparse
    import matplotlib.pyplot as plt

    ap = argparse.ArgumentParser(description="Summarize and visualize results.")
    ap.add_argument("--quant_baseline", default=str(Path("results_topk_baseline") / "run_results_topk_baseline.csv"))
    ap.add_argument("--quant_opt", default=str(Path("results_topk_optimized") / "run_results_topk_optimized.csv"))
    ap.add_argument("--judge_baseline", default=str(Path("results_llm_as_judge_baseline") / "judgement_summary.csv"))
    ap.add_argument("--judge_opt", default=str(Path("results_llm_as_judge_optimized") / "judgement_summary.csv"))

    args = ap.parse_args()

    fig, summaries = render_charts(
        quant_baseline=Path(args.quant_baseline),
        quant_optimized=Path(args.quant_opt),
        judge_baseline=Path(args.judge_baseline),
        judge_optimized=Path(args.judge_opt),
    )
    print_text_summaries(summaries)
    plt.show()


def build_markdown_summary(
    *,
    quant_baseline: Path = Path("results_topk_baseline") / "run_results_topk_baseline.csv",
    quant_optimized: Path = Path("results_topk_optimized") / "run_results_topk_optimized.csv",
    judge_baseline: Path = Path("results_llm_as_judge_baseline") / "judgement_summary.csv",
    judge_optimized: Path = Path("results_llm_as_judge_optimized") / "judgement_summary.csv",
) -> str:
    """Return a Markdown table comparing baseline vs optimized metrics with deltas.

    This is a pure function that reads the CSVs and produces Markdown suitable for Jupyter display.
    """
    summaries = summarize_groups(
        quant_paths={
            "baseline": Path(quant_baseline),
            "optimized": Path(quant_optimized),
        },
        judge_paths={
            "baseline": Path(judge_baseline),
            "optimized": Path(judge_optimized),
        },
    )

    base = summaries["baseline"]
    opt = summaries["optimized"]

    def _fmt(x: Optional[float], n: int = 3) -> str:
        return (f"{x:.{n}f}" if x is not None else "NA")

    def _sign(x: float) -> str:
        return "+" if x > 0 else ""

    rows: List[str] = []

    def _add_row(label: str, b: Optional[float], o: Optional[float], places: int) -> None:
        delta_str = "NA"
        if b is not None and o is not None:
            delta = o - b
            delta_str = f"{_sign(delta)}{_fmt(delta, places)}"
        rows.append(
            f"| {label:<27} | {_fmt(b, places):>8} | {_fmt(o, places):>9} | {delta_str:>13} |"
        )

    header = (
        "| Metric                      | Baseline | Optimized | Δ (Opt − Base) |\n"
        "|----------------------------|---------:|----------:|---------------:|"
    )

    _add_row("Avg Time (s)", base.avg_time_s, opt.avg_time_s, 3)
    _add_row("Peak Memory (KB)", base.avg_peak_kb, opt.avg_peak_kb, 1)
    _add_row("Exact (%)", (base.exact_rate * 100.0), (opt.exact_rate * 100.0), 1)
    _add_row("Sorted (%)", (base.sorted_rate * 100.0), (opt.sorted_rate * 100.0), 1)
    _add_row("LLM Adherence (1–5)", base.avg_adherence, opt.avg_adherence, 2)
    _add_row("Code Quality (1–5)", base.avg_code_quality, opt.avg_code_quality, 2)

    body = "\n".join(rows)
    md = f"### Prompt Optimization Results - Coding Tasks\n\n{header}\n{body}"
    return md
