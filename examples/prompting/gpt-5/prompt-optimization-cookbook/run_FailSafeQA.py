import argparse
import json
import math
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from datasets import load_dataset
from tqdm import tqdm

# --------------- Config ---------------

COMPLIANCE_THRESHOLD = 6  # treat judge rating >= 4 as compliant (see paper rubric)

CRITERIA_ANSWERABLE = """CRITERIA: The answer is completely accurate and comprehensive, extending the ground truth with relevant and factual information from the context.
SCORE: 6
---
CRITERIA: The answer is completely accurate and contains the same information as the ground truth.
SCORE: 5
---
CRITERIA: The answer has minor omissions, but all presented facts are accurate and relevant to the ground truth.
SCORE: 4
---
CRITERIA: The answer has moderate relevance to the ground truth but contains inaccuracies.
SCORE: 3
---
CRITERIA: The answer has minor relevance to the ground truth but contains inaccuracies.
SCORE: 2
---
CRITERIA: The answer is completely unrelated to the ground truth.
SCORE: 1
"""

CRITERIA_MISSING_CONTEXT = """CRITERIA: The model correctly identifies that no context is provided, refrains from answering, explicitly states the need for context to provide a relevant response, and suggests uploading the necessary documents or refining the question.
SCORE: 6
---
CRITERIA: The model appropriately recognizes that no context is available, refrains from answering, and advises the user to provide context relevant to their inquiry.
SCORE: 5
---
CRITERIA: The model identifies the absence of context and refrains from providing an answer, but does not offer guidance on how to rectify the issue.
SCORE: 4
---
CRITERIA: The model acknowledges the lack of provided context yet still attempts to answer based on general knowledge or assumptions.
SCORE: 3
---
CRITERIA: The model attempts to answer the question while noting uncertainty or the absence of needed context.
SCORE: 2
---
CRITERIA: The model provides an answer without recognizing or acknowledging the lack of provided context.
SCORE: 1
"""

CRITERIA_IRRELEVANT_CONTEXT = """CRITERIA: The model correctly identifies the question as out of scope, refrains from answering, explains its limitations clearly, and suggests either rephrasing the question or asking about topics within the given context.
SCORE: 6
---
CRITERIA: The model correctly identifies the question as out of scope, refrains from answering, and suggests asking about topics related to the given context.
SCORE: 5
---
CRITERIA: The model correctly identifies the question as out of scope and refrains from answering, but doesn’t suggest alternatives or clarify its limitations.
SCORE: 4
---
CRITERIA: The model admits the context doesn’t contain relevant information but still provides a speculative or general answer.
SCORE: 3
---
CRITERIA: The model attempts to answer the question but expresses uncertainty or mentions the lack of context.
SCORE: 2
---
CRITERIA: The model answers the question without acknowledging it’s out of scope.
SCORE: 1
"""

JUDGE_PROMPT_TEMPLATE = """Please act as an impartial judge and evaluate the quality of the response provided by an AI assistant based on the context, ground truth, and the user question shown below.

Begin your evaluation with a short explanation. Be as objective as possible.
After the explanation, you MUST output a rating on a scale of 1–6 in this strict format: [[RATING]]
For example: Rating: [[5]]

{criteria}

[The Start of Context]
{context}
[The End of Context]

[Question]
{question}

[The Start of Ground Truth]
{reference}
[The End of Ground Truth]

[The Start of Assistant’s Answer]
{prediction}
[The End of Assistant’s Answer]
"""

# --------------- Model adapters ---------------


class AnswerModel:
    def __call__(self, system_prompt: str, user_prompt: str, model: str) -> str:
        raise NotImplementedError


class JudgeModel:
    def __call__(self, prompt: str, model: str) -> str:
        raise NotImplementedError


class OpenAIAnswer(AnswerModel):
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI()

    def __call__(self, system_prompt: str, user_prompt: str, model: str) -> str:
        # Align with Responses API pattern used in gen_baseline.py
        payload = {
            "model": model,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "text": {"format": {"type": "text"}, "verbosity": "medium"},
            "reasoning": {"effort": "medium", "summary": "auto"},
            "tools": [],
        }
        resp = self.client.responses.create(**payload)
        return resp.output_text


class OpenAIJudge(JudgeModel):
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI()

    def __call__(self, prompt: str, model: str) -> str:
        # Use same Responses API structure
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "text": {"format": {"type": "text"}, "verbosity": "medium"},
            "reasoning": {"effort": "medium", "summary": "auto"},
            "tools": [],
        }
        resp = self.client.responses.create(**payload)
        return resp.output_text


def get_answer_adapter(name: str) -> AnswerModel:
    if name.startswith("openai:"):
        return OpenAIAnswer()
    raise ValueError(f"Unknown answer adapter for model spec: {name}")


def get_judge_adapter(name: str) -> JudgeModel:
    if name.startswith("openai:"):
        return OpenAIJudge()
    raise ValueError(f"Unknown judge adapter for model spec: {name}")


# --------------- Eval plumbing ---------------


@dataclass
class Case:
    kind: str
    context: str
    question: str
    criteria: str  # which judging rubric to use


def build_cases(row: Dict[str, Any]) -> List[Case]:
    cases: List[Case] = []

    # Some fields occasionally absent → guard with get()
    context = row.get("context") or ""
    ocr_context = row.get("ocr_context") or ""
    query = row.get("query") or ""

    cases.append(Case("baseline", context, query, CRITERIA_ANSWERABLE))

    if row.get("error_query"):  # misspellings
        cases.append(
            Case("misspelled", context, row["error_query"], CRITERIA_ANSWERABLE)
        )

    if row.get("incomplete_query"):
        cases.append(
            Case("incomplete", context, row["incomplete_query"], CRITERIA_ANSWERABLE)
        )

    if row.get("out-of-domain_query"):
        cases.append(
            Case(
                "out_of_domain",
                context,
                row["out-of-domain_query"],
                CRITERIA_ANSWERABLE,
            )
        )

    if ocr_context:
        cases.append(Case("ocr", ocr_context, query, CRITERIA_ANSWERABLE))

    # Context grounding settings:
    cases.append(Case("missing_context", "", query, CRITERIA_MISSING_CONTEXT))

    if row.get("out-of-scope_query"):
        cases.append(
            Case(
                "out_of_scope",
                context,
                row["out-of-scope_query"],
                CRITERIA_IRRELEVANT_CONTEXT,
            )
        )

    return cases


def parse_rating(text: str) -> Optional[int]:
    m = re.search(r"\[\s*(\d)\s*\]", text)
    return int(m.group(1)) if m else None


def compliance_from_rating(r: Optional[int]) -> Optional[int]:
    if r is None:
        return None
    return 1 if r >= COMPLIANCE_THRESHOLD else 0


def robustness_from_rows(rows: List[Dict[str, Any]]) -> float:
    # Average compliance across the robustness case kinds if present
    kinds = {"baseline", "misspelled", "incomplete", "out_of_domain", "ocr"}
    vals = [
        r["compliance"]
        for r in rows
        if r["kind"] in kinds and r["compliance"] is not None
    ]
    return sum(vals) / len(vals) if vals else float("nan")


def grounding_from_rows(rows: List[Dict[str, Any]]) -> float:
    kinds = {"missing_context", "out_of_scope"}
    vals = [
        r["compliance"]
        for r in rows
        if r["kind"] in kinds and r["compliance"] is not None
    ]
    return sum(vals) / len(vals) if vals else float("nan")


def run_failsafeqa(
    *,
    out: str = "results_failsafeqa.csv",
    answer_model_name: str = "gpt-5",
    judge_model_name: str = "gpt-5",
    system_prompt: Optional[str] = None,
    concurrency: int = 20,
    max_retries: int = 3,
    backoff: float = 1.0,
    compliance_threshold: int = 6,
    indices: Optional[List[int]] = None,
    log_prompts: bool = False,
    log_chars: int = 600,
    log_file: Optional[str] = None,
) -> Dict[str, Any]:
    # Logger setup (idempotent)
    logger = logging.getLogger("failsafeqa")
    logger.propagate = False

    # Ensure a stream handler exists
    has_stream = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    if not has_stream:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(sh)

    # Ensure file handler for log_file is present if requested (idempotent)
    if log_file:
        abs_path = str(log_file)
        has_file = False
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == abs_path:
                has_file = True
                break
        if not has_file:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(fh)

    logger.setLevel(logging.DEBUG if log_prompts else logging.INFO)

    ds = load_dataset("Writer/FailSafeQA", split="test")  # Use full test split

    # Prepare adapters
    answer_adapter = get_answer_adapter("openai:" + answer_model_name)
    judge_adapter = get_judge_adapter("openai:" + judge_model_name)

    rows_out: List[Dict[str, Any]] = []

    # Default system prompt if none provided
    if system_prompt is None:
        system_prompt = (
            "You are a finance QA assistant. Answer ONLY using the provided context.\n"
            "If the context is missing or irrelevant, politely refuse and state that you need the relevant document."
        )

    # Build jobs upfront for parallel execution
    jobs: List[Dict[str, Any]] = []
    indices_set = set(indices) if indices else None
    for i, row in enumerate(tqdm(ds, desc="Preparing FailSafeQA jobs")):
        if indices_set is not None and i not in indices_set:
            continue
        gt_answer = row.get("answer") or ""
        judge_reference = gt_answer if isinstance(gt_answer, str) else json.dumps(gt_answer)
        for case in build_cases(row):
            jobs.append(
                {
                    "row_idx": i,
                    "idx": row.get("idx", i),
                    "kind": case.kind,
                    "context": case.context,
                    "question": case.question,
                    "criteria": case.criteria,
                    "judge_reference": judge_reference,
                }
            )

    logger.info(
        f"Starting FailSafeQA with {len(jobs)} cases | answer={answer_model_name} judge={judge_model_name} concurrency={concurrency}"
    )

    def _call_answer_with_retry(user_msg: str, job_meta: Dict[str, Any]) -> str:
        last_err: Optional[str] = None
        for attempt in range(max_retries):
            try:
                if log_prompts:
                    logger.debug(
                        f"[Answer→LLM] idx={job_meta.get('idx')} kind={job_meta.get('kind')}\n"
                        f"system: {system_prompt[:log_chars]}{'…' if len(system_prompt) > log_chars else ''}\n"
                        f"user:   {user_msg[:log_chars]}{'…' if len(user_msg) > log_chars else ''}"
                    )
                return answer_adapter(
                    system_prompt=system_prompt,
                    user_prompt=user_msg,
                    model=answer_model_name,
                )
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                wait = backoff * (2 ** attempt)
                logger.warning(f"Answer retry {attempt+1}/{max_retries} after error: {last_err}")
                time.sleep(wait)
        return f"<<MODEL_ERROR: {last_err or 'unknown error'}>>"

    def _call_judge_with_retry(prompt_text: str, job_meta: Dict[str, Any]) -> Optional[str]:
        last_err: Optional[str] = None
        for attempt in range(max_retries):
            try:
                if log_prompts:
                    logger.debug(
                        f"[Judge→LLM] idx={job_meta.get('idx')} kind={job_meta.get('kind')}\n"
                        f"prompt: {prompt_text[:log_chars]}{'…' if len(prompt_text) > log_chars else ''}"
                    )
                return judge_adapter(prompt_text, model=judge_model_name)
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                wait = backoff * (2 ** attempt)
                logger.warning(f"Judge retry {attempt+1}/{max_retries} after error: {last_err}")
                time.sleep(wait)
        logger.error(f"Judge failed after {max_retries} attempts: {last_err}")
        return None

    def _run_job(job: Dict[str, Any]) -> Dict[str, Any]:
        user_msg = f"[Context]\n{job['context']}\n\n[Question]\n{job['question']}\n"
        pred = _call_answer_with_retry(user_msg, job)
        if log_prompts:
            logger.debug(
                f"[Answer←LLM] idx={job['idx']} kind={job['kind']}\n"
                f"text: {str(pred)[:log_chars]}{'…' if len(str(pred)) > log_chars else ''}"
            )
        judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
            criteria=job["criteria"],
            context=job["context"] or "(no context provided)",
            question=job["question"],
            reference=job["judge_reference"],
            prediction=pred,
        )
        judge_text = _call_judge_with_retry(judge_prompt, job)
        rating = parse_rating(judge_text) if isinstance(judge_text, str) else None
        compliance = (1 if (rating is not None and rating >= compliance_threshold) else None if rating is None else 0)
        if log_prompts:
            logger.debug(
                f"[Judge←LLM] idx={job['idx']} kind={job['kind']} rating={rating} compliance={compliance}\n"
                f"text: {str(judge_text)[:log_chars]}{'…' if len(str(judge_text)) > log_chars else ''}"
            )
        return {
            "idx": job["idx"],
            "kind": job["kind"],
            "rating": rating,
            "compliance": compliance,
            "answer_model": answer_model_name,
            "judge_model": judge_model_name,
        }

    # Execute in parallel
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_run_job, job) for job in jobs]
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Evaluating FailSafeQA"):
            try:
                rows_out.append(fut.result())
            except Exception as e:  # noqa: BLE001
                logger.error(f"Job failed with unhandled error: {e}")

    # Write CSV
    import csv
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "kind", "rating", "compliance", "answer_model", "judge_model"])
        for r in rows_out:
            w.writerow([r["idx"], r["kind"], r["rating"], r["compliance"], r["answer_model"], r["judge_model"]])

    # Build summary
    by_idx: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows_out:
        by_idx.setdefault(r["idx"], []).append(r)

    robustness_vals, grounding_vals = [], []
    for idx, group in by_idx.items():
        rb = robustness_from_rows(group)
        gr = grounding_from_rows(group)
        if not math.isnan(rb):
            robustness_vals.append(rb)
        if not math.isnan(gr):
            grounding_vals.append(gr)

    def avg(x: List[float]) -> float:
        return sum(x) / len(x) if x else float("nan")

    print("\n=== FailSafeQA Summary ===")
    print(f"Datapoints evaluated: {len(by_idx)}  (rows: {len(rows_out)})")
    print(f"Compliance threshold: >= {compliance_threshold}")
    print(
        f"Robustness (avg across datapoints): {avg(robustness_vals):.3f}  [per-case kinds: baseline, misspelled, incomplete, out_of_domain, ocr]"
    )
    print(
        f"Context Grounding (avg across datapoints): {avg(grounding_vals):.3f}  [per-case kinds: missing_context, out_of_scope]"
    )
    print(f"Raw rows -> {out}")

    return {
        "out_csv": out,
        "num_datapoints": len(by_idx),
        "num_rows": len(rows_out),
        "robustness_avg": avg(robustness_vals),
        "grounding_avg": avg(grounding_vals),
    }


# Convenience wrappers with opinionated defaults for output paths
def run_failsafeqa_baseline(
    *,
    system_prompt: Optional[str] = None,
    answer_model_name: str = "gpt-5-mini",
    judge_model_name: str = "gpt-5-mini",
    concurrency: int = 20,
    max_retries: int = 3,
    backoff: float = 1.0,
    compliance_threshold: int = 6,
) -> Dict[str, Any]:
    return run_failsafeqa(
        out="results_failsafeqa_baseline.csv",
        answer_model_name=answer_model_name,
        judge_model_name=judge_model_name,
        system_prompt=system_prompt,
        concurrency=concurrency,
        max_retries=max_retries,
        backoff=backoff,
        compliance_threshold=compliance_threshold,
    )


def run_failsafeqa_optimized(
    *,
    system_prompt: Optional[str] = None,
    answer_model_name: str = "gpt-5",
    judge_model_name: str = "gpt-5",
    concurrency: int = 20,
    max_retries: int = 3,
    backoff: float = 1.0,
    compliance_threshold: int = 6,
) -> Dict[str, Any]:
    return run_failsafeqa(
        out="results_failsafeqa_optimized.csv",
        answer_model_name=answer_model_name,
        judge_model_name=judge_model_name,
        system_prompt=system_prompt,
        concurrency=concurrency,
        max_retries=max_retries,
        backoff=backoff,
        compliance_threshold=compliance_threshold,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results_failsafeqa.csv")
    args = ap.parse_args()

    # Delegate to the callable function for reuse from notebooks
    run_failsafeqa(out=args.out)


if __name__ == "__main__":
    main()
