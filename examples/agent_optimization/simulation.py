"""Deterministic teaching simulation, token estimates, and response checks."""

import json
import math
import textwrap
from typing import Any

from support import (
    BAD_BASELINE_PROMPT,
    CONTROLLED_PROMPT,
    POLICIES,
    SLIM_TOOLS,
    STABLE_SUPPORT_PREFIX,
    VERBOSE_TOOLS,
    create_refund_case,
    escalate_to_human,
    lookup_customer,
    lookup_order,
    lookup_policy,
)

# Standard text-token rates, verified 2026-09-14 against the linked model pages.
MODEL_PRICES_USD_PER_1M = {
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "cached_input": 0.02, "output": 1.25},
}


def approx_tokens(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True)
    return max(1, math.ceil(len(value) / 4))


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    discount: float = 1.0,
) -> float:
    rates = MODEL_PRICES_USD_PER_1M[model]
    cached = min(cached_input_tokens, input_tokens)
    uncached = max(input_tokens - cached, 0)
    cost = (
        uncached * rates["input"]
        + cached * rates["cached_input"]
        + output_tokens * rates["output"]
    ) / 1_000_000
    return cost * discount


def response_usage_dict(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "input_tokens": 0,
            "cached_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
        }
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cached_tokens = getattr(input_details, "cached_tokens", 0) if input_details else 0
    reasoning_tokens = (
        getattr(output_details, "reasoning_tokens", 0) if output_details else 0
    )
    return {
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens or 0,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens or 0,
        "total_tokens": getattr(usage, "total_tokens", input_tokens + output_tokens)
        or input_tokens + output_tokens,
    }


VARIANT_ORDER = [
    "00_bad_baseline",
    "01_prompt_tool_context_controls",
    "02_model_routing",
    "03_prompt_caching",
    "04_split_workflow",
]

VARIANT_LABELS = {
    "00_bad_baseline": "Bad baseline",
    "01_prompt_tool_context_controls": "Round 1: controls",
    "02_model_routing": "Round 2: routing",
    "03_prompt_caching": "Round 3: caching",
    "04_split_workflow": "Round 4: split workflow",
}

CACHE_ELIGIBILITY_MIN_TOKENS = (
    1024  # Simplified demo threshold; actual eligibility varies.
)
CONCISE_OUTPUT_TOKEN_LIMIT = 120
ASYNC_BATCH_DISCOUNT = 0.50  # Batch API discount; verified 2026-09-14.

STABLE_POLICY_DIGEST = textwrap.dedent(
    """
    Stable support playbook digest:
    - Shipping delays: provide status, ETA, and tracking next steps; do not refund solely for short carrier delays.
    - Delivered-not-received: verify delivery details, ask the customer to check common locations, and start carrier trace steps when appropriate.
    - Damaged delivery: request photo evidence before offering replacement or refund; high-value damaged items require human review.
    - Refunds: standard returnable items are eligible within 30 days; outside-window or high-value disputes require human review.
    - Billing: duplicate-charge reports require billing review; acknowledge and escalate, but do not promise a completed refund.
    - Account access: when identity is not verified, escalate to account security; do not change credentials or contact information in chat.
    - Customer messages must be concise, policy-compliant, and explicit about next steps.
    - Internal notes, raw carrier payloads, CRM audit logs, and policy appendices must never be exposed to the customer.
    """
).strip()

# Repeat the stable digest to mimic a real support playbook plus stable tool/schema prefix.
# This makes prompt caching eligible without adding volatile ticket-specific content.
CACHE_FRIENDLY_PROMPT = (
    STABLE_SUPPORT_PREFIX + "\n\n" + "\n".join([STABLE_POLICY_DIGEST] * 5)
)

DIFFICULTY_REASONING_BASE = {
    "simple_lookup": 45,
    "routine_policy": 70,
    "sensitive_policy": 95,
    "account_security": 125,
    "outside_policy_window": 120,
    "high_value_policy": 135,
}

MODEL_LATENCY_BASE = {
    "gpt-5.4": 0.95,
    "gpt-5.4-mini": 0.35,
    "gpt-5.4-nano": 0.16,
}

ALL_TOOL_NAMES = [tool["name"] for tool in SLIM_TOOLS]


def tools_for_ticket(ticket: dict[str, Any], variant: str) -> list[str]:
    if variant == "00_bad_baseline":
        return ALL_TOOL_NAMES.copy()
    return ticket["expected_tools"].copy()


def route_resolution_model(ticket: dict[str, Any], variant: str) -> str:
    if variant in {"00_bad_baseline", "01_prompt_tool_context_controls"}:
        return "gpt-5.4"
    if ticket["risk"] == "high":
        return "gpt-5.4"
    return "gpt-5.4-mini"


def action_for_ticket(ticket: dict[str, Any], variant: str) -> str:
    if variant != "00_bad_baseline":
        return ticket["expected_action"]

    # The baseline is intentionally inefficient and sometimes over- or under-acts.
    baseline_mistakes = {
        "damaged_delivery": "open_replacement_without_photo",
        "refund_eligibility": "escalate_refund_review",
        "high_value_damage": "promise_refund_high_value_damage",
    }
    return baseline_mistakes.get(ticket["intent"], ticket["expected_action"])


def action_is_escalation(action: str) -> bool:
    return action.startswith("escalate_")


def simulated_customer_response(
    ticket: dict[str, Any], variant: str, action: str
) -> str:
    order_id = ticket.get("order_id") or "your account"
    if variant == "00_bad_baseline":
        return textwrap.dedent(
            f"""
            I reviewed your message for ticket {ticket["ticket_id"]} and checked the customer profile, order system,
            policy library, refund workflow, escalation queue, carrier events, billing signals, and internal audit notes.
            Based on the available context for {order_id}, the detected intent is {ticket["intent"]} and the risk level is
            {ticket["risk"]}. I also compared this against the {ticket["expected_policy"]} policy and related internal
            exceptions. My working action is `{action}`. I am including this detail so you understand each step, but some
            of these details are internal operational records. The next step is to proceed according to that action, and
            we may need additional review if any policy exception applies.
            """
        ).strip()

    if action == "provide_status_eta":
        return "Your order is still in transit and the latest ETA is tomorrow. The carrier shows a short delay, so no refund is due yet. Please check the tracking link again tomorrow."
    if action == "request_photo_then_offer_replacement":
        return "I can help with a replacement. Please reply with a photo of the cracked blender and packaging, and we can start the replacement or refund process under the damaged-delivery policy."
    if action == "open_refund_case":
        return f"This order arrived within 30 days and is eligible for a return, so I opened a refund case for {order_id}. You will receive return instructions and the refund will be processed after the return is received."
    if action == "escalate_billing_review":
        return "I found a duplicate-charge signal and sent this to billing review. The billing team will verify the charge before any refund is confirmed."
    if action == "escalate_account_security":
        return "I cannot change account details until identity verification is complete. I escalated this to account security so they can help you recover access safely."
    if action == "escalate_refund_review":
        return "This refund request is outside the standard window, so I escalated it for human review. A specialist will check whether an exception applies."
    if action == "start_delivery_trace_steps":
        return "Tracking shows the order was delivered today. Please check common delivery spots and confirm the address; if it is still missing, we can start carrier trace steps."
    if action == "escalate_high_value_damage":
        return "I am sorry the item arrived damaged. Because this is a high-value item, I escalated it for human review. Please attach photos of the item and packaging."
    return "I reviewed the ticket and sent it to the right support path."


def simulated_reasoning_tokens(
    ticket: dict[str, Any], variant: str, model: str, tool_count: int
) -> int:
    base = DIFFICULTY_REASONING_BASE[ticket["difficulty"]]
    if variant == "00_bad_baseline":
        return int(base + 260 + tool_count * 28)
    if variant == "01_prompt_tool_context_controls":
        return int(base * 0.72 + tool_count * 10)
    if variant in {"02_model_routing", "03_prompt_caching"}:
        model_factor = 0.62 if model == "gpt-5.4-mini" else 0.82
        return int(base * model_factor + tool_count * 8)
    model_factor = 0.55 if model == "gpt-5.4-mini" else 0.74
    return int(base * model_factor + tool_count * 6)


def prompt_for_variant(variant: str) -> str:
    if variant == "00_bad_baseline":
        return BAD_BASELINE_PROMPT
    if variant in {"03_prompt_caching", "04_split_workflow"}:
        return CACHE_FRIENDLY_PROMPT
    return CONTROLLED_PROMPT


def evaluate_trace_quality(
    ticket: dict[str, Any],
    tools: list[str],
    action: str,
    visible_output_tokens: int,
    model: str,
    customer_response: str,
) -> dict[str, Any]:
    """Check labels and literal response phrases; this is not a semantic judge."""
    expected_tools = set(ticket["expected_tools"])
    called_tools = set(tools)
    missing_tools = sorted(expected_tools - called_tools)
    extra_tools = sorted(called_tools - expected_tools)
    escalation_correct = action_is_escalation(action) == ticket["must_escalate"]
    action_correct = action == ticket["expected_action"]
    concise = visible_output_tokens <= CONCISE_OUTPUT_TOKEN_LIMIT
    normalized_response = " ".join(customer_response.casefold().split())
    missing_phrases = [
        phrase
        for phrase in ticket["expected_customer_response_contains"]
        if " ".join(phrase.casefold().split()) not in normalized_response
    ]
    forbidden_claims = [
        phrase
        for phrase in ticket["forbidden_response_claims"]
        if " ".join(phrase.casefold().split()) in normalized_response
    ]
    response_complete = bool(normalized_response) and not missing_phrases
    forbidden_claims_absent = not forbidden_claims
    policy_compliant = (
        escalation_correct
        and action_correct
        and not missing_tools
        and response_complete
        and forbidden_claims_absent
    )

    score = 0.98
    if not response_complete:
        score -= 0.25
    if not forbidden_claims_absent:
        score -= 0.40
    if missing_tools:
        score -= 0.24
    if not action_correct:
        score -= 0.18
    if not escalation_correct:
        score -= 0.20
    if not concise:
        score -= 0.08
    score -= min(0.14, 0.025 * len(extra_tools))
    if ticket["risk"] == "high" and model != "gpt-5.4":
        score -= 0.06
    if ticket["risk"] == "high" and model == "gpt-5.4" and policy_compliant:
        score += 0.02

    return {
        "missing_required_tools": ", ".join(missing_tools),
        "extra_tool_calls": len(extra_tools),
        "unnecessary_tools": ", ".join(extra_tools),
        "escalation_correct": escalation_correct,
        "action_correct": action_correct,
        "policy_compliant": policy_compliant,
        "concise": concise,
        "response_complete": response_complete,
        "missing_required_phrases": ", ".join(missing_phrases),
        "forbidden_claims_absent": forbidden_claims_absent,
        "forbidden_claims_found": ", ".join(forbidden_claims),
        "quality_score": round(max(0.0, min(0.99, score)), 2),
    }


def simulate_trace(ticket: dict[str, Any], variant: str) -> dict[str, Any]:
    model = route_resolution_model(ticket, variant)
    tools = tools_for_ticket(ticket, variant)
    action = action_for_ticket(ticket, variant)
    payload_mode = "verbose" if variant == "00_bad_baseline" else "slim"
    tool_schema = VERBOSE_TOOLS if variant == "00_bad_baseline" else SLIM_TOOLS
    prompt = prompt_for_variant(variant)

    prompt_tokens = approx_tokens(prompt)
    schema_tokens = approx_tokens(tool_schema)
    user_tokens = approx_tokens(
        {k: ticket[k] for k in ["ticket_id", "customer_id", "message", "order_id"]}
    )
    carried_context_tokens = {
        "00_bad_baseline": 1250,
        "01_prompt_tool_context_controls": 280,
        "02_model_routing": 220,
        "03_prompt_caching": 220,
        "04_split_workflow": 140,
    }[variant]

    tool_results = []
    for name in tools:
        if name == "lookup_customer":
            arguments = {"customer_id": ticket["customer_id"]}
            result = lookup_customer(**arguments, payload=payload_mode)
        elif name == "lookup_order" and ticket.get("order_id"):
            arguments = {"order_id": ticket["order_id"]}
            result = lookup_order(**arguments, payload=payload_mode)
        elif name == "lookup_policy":
            arguments = {"topic": ticket["expected_policy"]}
            result = lookup_policy(**arguments, payload=payload_mode)
        elif name == "create_refund_case" and ticket.get("order_id"):
            arguments = {"order_id": ticket["order_id"], "reason": ticket["intent"]}
            result = create_refund_case(**arguments)
        elif name == "escalate_to_human":
            arguments = {"ticket_id": ticket["ticket_id"], "reason": ticket["intent"]}
            result = escalate_to_human(**arguments)
        else:
            continue
        tool_results.append({"name": name, "arguments": arguments, "result": result})
    tool_output_tokens = sum(approx_tokens(call["result"]) for call in tool_results)

    background_sync_tokens = {
        "00_bad_baseline": 900,
        "01_prompt_tool_context_controls": 220,
        "02_model_routing": 180,
        "03_prompt_caching": 180,
        "04_split_workflow": 0,
    }[variant]

    input_tokens = (
        prompt_tokens
        + schema_tokens
        + user_tokens
        + carried_context_tokens
        + tool_output_tokens
        + background_sync_tokens
    )

    customer_response = simulated_customer_response(ticket, variant, action)
    visible_output_tokens = approx_tokens(customer_response)
    reasoning_tokens = simulated_reasoning_tokens(ticket, variant, model, len(tools))
    output_tokens = visible_output_tokens + reasoning_tokens

    routing_cost = 0.0
    routing_tokens = 0
    if variant in {"02_model_routing", "03_prompt_caching", "04_split_workflow"}:
        routing_input = (
            approx_tokens(
                {"message": ticket["message"], "known_order_id": ticket.get("order_id")}
            )
            + 140
        )
        routing_output = 42
        routing_tokens = routing_input + routing_output
        routing_cost = estimate_cost_usd("gpt-5.4-nano", routing_input, routing_output)

    cached_tokens = 0
    cacheable_prefix_tokens = 0
    if variant in {"03_prompt_caching", "04_split_workflow"}:
        cacheable_prefix_tokens = prompt_tokens + schema_tokens
        if (
            input_tokens >= CACHE_ELIGIBILITY_MIN_TOKENS
            and cacheable_prefix_tokens >= CACHE_ELIGIBILITY_MIN_TOKENS
        ):
            cached_tokens = min(cacheable_prefix_tokens, input_tokens)

    sync_cost = (
        estimate_cost_usd(model, input_tokens, output_tokens, cached_tokens)
        + routing_cost
    )

    background_cost = 0.0
    background_tokens = 0
    if variant == "04_split_workflow":
        background_input_tokens = (
            approx_tokens(
                {"ticket": ticket, "policy": POLICIES[ticket["expected_policy"]]}
            )
            + 260
        )
        background_output_tokens = 90
        background_tokens = background_input_tokens + background_output_tokens
        background_cost = estimate_cost_usd(
            "gpt-5.4-nano",
            background_input_tokens,
            background_output_tokens,
            discount=ASYNC_BATCH_DISCOUNT,
        )

    sync_tokens = input_tokens + output_tokens + routing_tokens

    latency_input_tokens = max(input_tokens - int(cached_tokens * 0.75), 0)

    latency_s = (
        0.28
        + MODEL_LATENCY_BASE[model]
        + latency_input_tokens / 5200
        + output_tokens / 3000
        + len(tools) * 0.14
        + (0.18 if routing_tokens else 0)
        + (0.38 if background_sync_tokens else 0)
    )

    quality = evaluate_trace_quality(
        ticket, tools, action, visible_output_tokens, model, customer_response
    )

    return {
        "variant": variant,
        "variant_label": VARIANT_LABELS[variant],
        "ticket_id": ticket["ticket_id"],
        "intent": ticket["intent"],
        "risk": ticket["risk"],
        "difficulty": ticket["difficulty"],
        "model": model,
        "routing_tokens": routing_tokens,
        "tool_calls": len(tools),
        "expected_tools": ", ".join(ticket["expected_tools"]),
        "tools": ", ".join(tools),
        "action": action,
        "expected_action": ticket["expected_action"],
        "input_tokens": input_tokens,
        "latency_input_tokens": latency_input_tokens,
        "cacheable_prefix_tokens": cacheable_prefix_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "visible_output_tokens": visible_output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "sync_tokens": sync_tokens,
        "total_tokens": sync_tokens + background_tokens,
        "latency_s": round(latency_s, 2),
        "sync_cost_usd": sync_cost,
        "background_tokens": background_tokens,
        "background_cost_usd": background_cost,
        "cost_usd": sync_cost + background_cost,
        "escalated": action_is_escalation(action),
        "customer_response": customer_response,
        "tool_results": tool_results,
        **quality,
    }


def deterministic_guardrail_check(
    ticket: dict[str, Any], trace: dict[str, Any]
) -> list[str]:
    failures = []
    if trace["missing_required_tools"]:
        failures.append("missing_required_tools")
    if trace["extra_tool_calls"] > 2:
        failures.append("too_many_unnecessary_tools")
    if not trace["response_complete"]:
        failures.append("missing_required_response_content")
    if not trace["forbidden_claims_absent"]:
        failures.append("forbidden_response_claim")
    if not trace["policy_compliant"]:
        failures.append("policy_or_action_mismatch")
    if not trace["escalation_correct"]:
        failures.append("escalation_mismatch")
    if not trace["concise"]:
        failures.append("customer_answer_too_long")
    if ticket["intent"] == "account_access" and not trace["escalated"]:
        failures.append("unsafe_account_access_resolution")
    return failures
