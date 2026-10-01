"""Synthetic support fixtures, local tools, and prompts; no external side effects."""

import textwrap
from typing import Any

EVAL_SET = [
    {
        "ticket_id": "T-001",
        "customer_id": "C-100",
        "message": "Where is order O-1001? It was supposed to arrive yesterday.",
        "intent": "order_status",
        "order_id": "O-1001",
        "risk": "low",
        "difficulty": "simple_lookup",
        "must_escalate": False,
        "expected_policy": "shipping",
        "expected_tools": ["lookup_order"],
        "expected_action": "provide_status_eta",
        "expected_resolution_type": "resolved",
        "expected_customer_response_contains": ["in transit", "tomorrow"],
        "forbidden_response_claims": ["refund completed", "replacement opened"],
    },
    {
        "ticket_id": "T-002",
        "customer_id": "C-200",
        "message": "My blender arrived cracked. Order O-1002. Can you replace it?",
        "intent": "damaged_delivery",
        "order_id": "O-1002",
        "risk": "medium",
        "difficulty": "routine_policy",
        "must_escalate": False,
        "expected_policy": "damaged_delivery",
        "expected_tools": ["lookup_order", "lookup_policy"],
        "expected_action": "request_photo_then_offer_replacement",
        "expected_resolution_type": "resolved_next_step",
        "expected_customer_response_contains": ["photo", "replacement"],
        "forbidden_response_claims": ["refund completed", "no photo needed"],
    },
    {
        "ticket_id": "T-003",
        "customer_id": "C-300",
        "message": "I want a refund for order O-1003. It arrived but I changed my mind.",
        "intent": "refund_eligibility",
        "order_id": "O-1003",
        "risk": "medium",
        "difficulty": "routine_policy",
        "must_escalate": False,
        "expected_policy": "refunds",
        "expected_tools": ["lookup_order", "lookup_policy", "create_refund_case"],
        "expected_action": "open_refund_case",
        "expected_resolution_type": "case_opened",
        "expected_customer_response_contains": ["refund case", "within 30 days"],
        "forbidden_response_claims": ["refund completed", "human review required"],
    },
    {
        "ticket_id": "T-004",
        "customer_id": "C-400",
        "message": "I was charged twice for order O-1004. Please fix this.",
        "intent": "billing_issue",
        "order_id": "O-1004",
        "risk": "medium",
        "difficulty": "sensitive_policy",
        "must_escalate": True,
        "expected_policy": "billing",
        "expected_tools": ["lookup_order", "lookup_policy", "escalate_to_human"],
        "expected_action": "escalate_billing_review",
        "expected_resolution_type": "escalated",
        "expected_customer_response_contains": ["billing", "review"],
        "forbidden_response_claims": ["refund completed", "duplicate charge reversed"],
    },
    {
        "ticket_id": "T-005",
        "customer_id": "C-500",
        "message": "I cannot get into my account and my phone number changed.",
        "intent": "account_access",
        "order_id": None,
        "risk": "high",
        "difficulty": "account_security",
        "must_escalate": True,
        "expected_policy": "account_access",
        "expected_tools": ["lookup_customer", "lookup_policy", "escalate_to_human"],
        "expected_action": "escalate_account_security",
        "expected_resolution_type": "escalated",
        "expected_customer_response_contains": ["account security", "verification"],
        "forbidden_response_claims": [
            "phone number changed",
            "password reset completed",
        ],
    },
    {
        "ticket_id": "T-006",
        "customer_id": "C-600",
        "message": "I want a refund for order O-1005, but tracking says delivered 45 days ago.",
        "intent": "refund_dispute",
        "order_id": "O-1005",
        "risk": "high",
        "difficulty": "outside_policy_window",
        "must_escalate": True,
        "expected_policy": "refunds",
        "expected_tools": ["lookup_order", "lookup_policy", "escalate_to_human"],
        "expected_action": "escalate_refund_review",
        "expected_resolution_type": "escalated",
        "expected_customer_response_contains": ["human review", "outside"],
        "forbidden_response_claims": ["refund completed", "refund case opened"],
    },
    {
        "ticket_id": "T-007",
        "customer_id": "C-700",
        "message": "Tracking says order O-1006 was delivered today, but I do not see it at my door.",
        "intent": "delivered_not_received",
        "order_id": "O-1006",
        "risk": "medium",
        "difficulty": "routine_policy",
        "must_escalate": False,
        "expected_policy": "shipping",
        "expected_tools": ["lookup_order", "lookup_policy"],
        "expected_action": "start_delivery_trace_steps",
        "expected_resolution_type": "resolved_next_step",
        "expected_customer_response_contains": ["delivered today", "check", "carrier"],
        "forbidden_response_claims": ["refund completed", "replacement opened"],
    },
    {
        "ticket_id": "T-008",
        "customer_id": "C-800",
        "message": "The espresso machine in order O-1007 arrived shattered. It was over $1,000 and I need a refund now.",
        "intent": "high_value_damage",
        "order_id": "O-1007",
        "risk": "high",
        "difficulty": "high_value_policy",
        "must_escalate": True,
        "expected_policy": "damaged_delivery",
        "expected_tools": ["lookup_order", "lookup_policy", "escalate_to_human"],
        "expected_action": "escalate_high_value_damage",
        "expected_resolution_type": "escalated",
        "expected_customer_response_contains": ["human review", "photo"],
        "forbidden_response_claims": ["refund completed", "replacement shipped"],
    },
    {
        "ticket_id": "T-009",
        "customer_id": "C-900",
        "message": "I need to return order O-1008. The headphones are unopened and arrived two weeks ago.",
        "intent": "refund_eligibility",
        "order_id": "O-1008",
        "risk": "low",
        "difficulty": "routine_policy",
        "must_escalate": False,
        "expected_policy": "refunds",
        "expected_tools": ["lookup_order", "lookup_policy", "create_refund_case"],
        "expected_action": "open_refund_case",
        "expected_resolution_type": "case_opened",
        "expected_customer_response_contains": ["refund case", "eligible"],
        "forbidden_response_claims": ["human review required", "refund completed"],
    },
    {
        "ticket_id": "T-010",
        "customer_id": "C-1000",
        "message": "I lost access to my account and cannot verify the old email address.",
        "intent": "account_access",
        "order_id": None,
        "risk": "high",
        "difficulty": "account_security",
        "must_escalate": True,
        "expected_policy": "account_access",
        "expected_tools": ["lookup_customer", "lookup_policy", "escalate_to_human"],
        "expected_action": "escalate_account_security",
        "expected_resolution_type": "escalated",
        "expected_customer_response_contains": ["account security", "verification"],
        "forbidden_response_claims": ["email changed", "account restored"],
    },
]


INTERNAL_POLICY_APPENDIX = (
    "Internal appendix: historical exception notes, vendor mappings, warehouse event definitions, "
    "billing processor flags, carrier SLA tables, outdated macro text, and audit metadata. "
    * 45
)

ORDERS = {
    "O-1001": {
        "order_id": "O-1001",
        "status": "in_transit",
        "carrier": "UPS",
        "eta": "tomorrow",
        "items": [{"sku": "MUG-11", "name": "Ceramic mug", "price": 18.0}],
        "delivered_days_ago": None,
        "payment_status": "paid_once",
        "events": ["packed", "carrier_pickup", "regional_delay", "in_transit"],
    },
    "O-1002": {
        "order_id": "O-1002",
        "status": "delivered",
        "carrier": "FedEx",
        "eta": None,
        "items": [{"sku": "BLD-42", "name": "Countertop blender", "price": 89.0}],
        "delivered_days_ago": 2,
        "payment_status": "paid_once",
        "events": ["packed", "carrier_pickup", "delivered", "damage_claim_available"],
    },
    "O-1003": {
        "order_id": "O-1003",
        "status": "delivered",
        "carrier": "USPS",
        "eta": None,
        "items": [{"sku": "SHOE-9", "name": "Running shoes", "price": 120.0}],
        "delivered_days_ago": 8,
        "payment_status": "paid_once",
        "events": ["packed", "delivered", "standard_return_window"],
    },
    "O-1004": {
        "order_id": "O-1004",
        "status": "delivered",
        "carrier": "UPS",
        "eta": None,
        "items": [{"sku": "COAT-3", "name": "Rain coat", "price": 150.0}],
        "delivered_days_ago": 4,
        "payment_status": "duplicate_charge_detected",
        "events": ["packed", "delivered", "billing_review_required"],
    },
    "O-1005": {
        "order_id": "O-1005",
        "status": "delivered",
        "carrier": "DHL",
        "eta": None,
        "items": [{"sku": "CAM-7", "name": "Camera kit", "price": 650.0}],
        "delivered_days_ago": 45,
        "payment_status": "paid_once",
        "events": ["packed", "delivered", "outside_standard_refund_window"],
    },
    "O-1006": {
        "order_id": "O-1006",
        "status": "delivered",
        "carrier": "UPS",
        "eta": None,
        "items": [{"sku": "LAMP-8", "name": "Desk lamp", "price": 46.0}],
        "delivered_days_ago": 0,
        "payment_status": "paid_once",
        "events": ["packed", "delivered", "proof_of_delivery_uploaded"],
    },
    "O-1007": {
        "order_id": "O-1007",
        "status": "delivered",
        "carrier": "FedEx",
        "eta": None,
        "items": [
            {"sku": "ESP-99", "name": "Prosumer espresso machine", "price": 1250.0}
        ],
        "delivered_days_ago": 1,
        "payment_status": "paid_once",
        "events": ["packed", "delivered", "damage_claim_available", "high_value_item"],
    },
    "O-1008": {
        "order_id": "O-1008",
        "status": "delivered",
        "carrier": "USPS",
        "eta": None,
        "items": [{"sku": "HP-21", "name": "Wireless headphones", "price": 75.0}],
        "delivered_days_ago": 14,
        "payment_status": "paid_once",
        "events": [
            "packed",
            "delivered",
            "standard_return_window",
            "unopened_customer_claim",
        ],
    },
}

CUSTOMERS = {
    "C-100": {
        "tier": "standard",
        "region": "CA",
        "verified": True,
        "lifetime_value": 240,
    },
    "C-200": {"tier": "plus", "region": "NY", "verified": True, "lifetime_value": 920},
    "C-300": {
        "tier": "standard",
        "region": "WA",
        "verified": True,
        "lifetime_value": 410,
    },
    "C-400": {
        "tier": "standard",
        "region": "IL",
        "verified": True,
        "lifetime_value": 310,
    },
    "C-500": {
        "tier": "plus",
        "region": "TX",
        "verified": False,
        "lifetime_value": 1250,
    },
    "C-600": {
        "tier": "standard",
        "region": "CA",
        "verified": True,
        "lifetime_value": 700,
    },
    "C-700": {
        "tier": "standard",
        "region": "OR",
        "verified": True,
        "lifetime_value": 155,
    },
    "C-800": {"tier": "plus", "region": "FL", "verified": True, "lifetime_value": 2800},
    "C-900": {
        "tier": "standard",
        "region": "MA",
        "verified": True,
        "lifetime_value": 190,
    },
    "C-1000": {
        "tier": "standard",
        "region": "AZ",
        "verified": False,
        "lifetime_value": 80,
    },
}

POLICIES = {
    "shipping": "If an order is in transit with a carrier delay, provide status, ETA, and tracking next steps. If tracking says delivered today but the customer cannot find it, ask them to check common delivery locations, verify the address, and start carrier trace steps if it remains missing. Do not refund solely for a short carrier delay or same-day delivered-not-received report.",
    "damaged_delivery": "If damage is reported within 7 days of delivery, ask for a photo and offer replacement or refund after evidence is collected. High-value damaged items over $1,000 require human review before promising a refund or replacement.",
    "refunds": "Standard refunds are eligible within 30 days of delivery for most unopened or returnable items. Orders over 30 days old, high-value disputes, or ambiguous return condition require human review before any refund promise.",
    "billing": "Duplicate charges require billing review. A support agent may acknowledge the issue and escalate, but must not promise a completed refund until billing verifies it.",
    "account_access": "If account recovery identity is not verified, escalate to account security. Do not change credentials, email addresses, or phone numbers in chat.",
}


def lookup_order(order_id: str, payload: str = "slim") -> dict[str, Any]:
    order = ORDERS.get(order_id.upper())
    if not order:
        return {"found": False, "order_id": order_id}
    if payload == "verbose":
        return {
            "found": True,
            "order": order,
            "warehouse_events": [
                {
                    "event": event,
                    "source": "wms",
                    "debug": INTERNAL_POLICY_APPENDIX[:300],
                }
                for event in order["events"]
            ],
            "carrier_payload": {
                "carrier": order["carrier"],
                "raw_tracking_blob": INTERNAL_POLICY_APPENDIX,
            },
            "payment_processor_payload": {
                "status": order["payment_status"],
                "raw_processor_notes": INTERNAL_POLICY_APPENDIX[:1200],
            },
            "internal_notes": INTERNAL_POLICY_APPENDIX,
        }
    return {
        "found": True,
        "order_id": order["order_id"],
        "status": order["status"],
        "carrier": order["carrier"],
        "eta": order["eta"],
        "delivered_days_ago": order["delivered_days_ago"],
        "payment_status": order["payment_status"],
        "item_value": sum(item["price"] for item in order["items"]),
        "events": [
            event
            for event in order["events"]
            if event
            in {
                "regional_delay",
                "damage_claim_available",
                "billing_review_required",
                "outside_standard_refund_window",
                "proof_of_delivery_uploaded",
                "high_value_item",
                "standard_return_window",
            }
        ],
    }


def lookup_customer(customer_id: str, payload: str = "slim") -> dict[str, Any]:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"found": False, "customer_id": customer_id}
    if payload == "verbose":
        return {
            "found": True,
            "customer_id": customer_id,
            "profile": customer,
            "all_recent_order_ids": list(ORDERS.keys()),
            "crm_audit_log": INTERNAL_POLICY_APPENDIX,
        }
    return {"found": True, "customer_id": customer_id, **customer}


def lookup_policy(topic: str, payload: str = "slim") -> dict[str, Any]:
    policy = POLICIES.get(topic)
    if not policy:
        return {"found": False, "topic": topic}
    if payload == "verbose":
        return {
            "found": True,
            "topic": topic,
            "policy": policy,
            "appendix": INTERNAL_POLICY_APPENDIX,
            "all_policy_topics": POLICIES,
        }
    return {"found": True, "topic": topic, "policy": policy}


def create_refund_case(order_id: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": f"RF-{order_id}",
        "order_id": order_id,
        "status": "opened",
        "reason": reason,
    }


def escalate_to_human(ticket_id: str, reason: str) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "queue": "human_support",
        "priority": "normal",
        "reason": reason,
    }


def function_schema(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "strict": True,
    }


VERBOSE_TOOLS = [
    function_schema(
        "lookup_customer",
        "Retrieve the complete customer CRM profile, including audit metadata, tiering data, account verification state, related orders, and any internal support notes that could possibly help.",
        {
            "customer_id": {
                "type": "string",
                "description": "The customer identifier from the ticket.",
            }
        },
        ["customer_id"],
    ),
    function_schema(
        "lookup_order",
        "Retrieve the complete order record, shipment timeline, billing fields, warehouse event payloads, raw carrier diagnostics, and internal debug data.",
        {
            "order_id": {
                "type": "string",
                "description": "The order identifier, such as O-1001.",
            }
        },
        ["order_id"],
    ),
    function_schema(
        "lookup_policy",
        "Retrieve the full policy topic, all related appendix material, exception examples, internal macros, and neighboring policy topics.",
        {
            "topic": {
                "type": "string",
                "enum": list(POLICIES),
                "description": "Policy topic to retrieve.",
            }
        },
        ["topic"],
    ),
    function_schema(
        "create_refund_case",
        "Open a refund case in the back office system. This should be used for any refund or replacement possibility, even when a human review might be required.",
        {
            "order_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        ["order_id", "reason"],
    ),
    function_schema(
        "escalate_to_human",
        "Escalate a ticket to a human support agent when the issue is ambiguous, policy-sensitive, high value, account-security related, or otherwise risky.",
        {
            "ticket_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        ["ticket_id", "reason"],
    ),
]

SLIM_TOOLS = [
    function_schema(
        "lookup_customer",
        "Fetch minimal customer verification and support tier fields.",
        {"customer_id": {"type": "string"}},
        ["customer_id"],
    ),
    function_schema(
        "lookup_order",
        "Fetch order status, delivery age, payment status, and item value.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    function_schema(
        "lookup_policy",
        "Fetch the policy needed for the current support decision.",
        {"topic": {"type": "string", "enum": list(POLICIES)}},
        ["topic"],
    ),
    function_schema(
        "create_refund_case",
        "Open a refund or replacement case only after policy eligibility is established.",
        {"order_id": {"type": "string"}, "reason": {"type": "string"}},
        ["order_id", "reason"],
    ),
    function_schema(
        "escalate_to_human",
        "Escalate a ticket that requires human review.",
        {"ticket_id": {"type": "string"}, "reason": {"type": "string"}},
        ["ticket_id", "reason"],
    ),
]


def allowed_tool_choice(names: list[str], mode: str = "auto") -> dict[str, Any]:
    return {
        "type": "allowed_tools",
        "mode": mode,
        "tools": [{"type": "function", "name": name} for name in names],
    }


BAD_BASELINE_PROMPT = textwrap.dedent(
    """
    You are a comprehensive customer support super-agent for an e-commerce company.

    Always be extremely thorough. Before answering, gather as much context as possible from
    customer, order, policy, refund, escalation, and internal support systems. Prefer using tools
    even when the answer may already be apparent. Include helpful background and explain your
    reasoning to the customer in detail so they understand every step.

    You are also responsible for post-resolution QA, analytics tags, support summaries, policy-gap
    mining, and escalation audits before you respond to the customer.

    If there is any uncertainty, call more tools. If a policy might be relevant, retrieve the policy.
    If an order might be relevant, retrieve the order. If customer history might be relevant, retrieve
    the customer profile.
    """
).strip()

CONTROLLED_PROMPT = textwrap.dedent(
    """
    Role: E-commerce support assistant.

    Goal: Resolve routine support tickets with the fewest necessary tool calls while preserving policy correctness.

    Tool rules:
    - Use only tools required for the current decision.
    - Order status: order lookup only.
    - Damaged delivery or refund: order lookup plus the relevant policy.
    - Billing duplicate charge: order lookup plus billing policy, then escalate.
    - Account access with unverified identity: customer lookup plus account policy, then escalate.

    Response rules:
    - Give the customer the outcome and next step.
    - Do not expose internal reasoning, raw tool data, audit notes, or policy text.
    - Keep the customer-facing answer under 120 words unless escalation legally requires more detail.
    """
).strip()

STABLE_SUPPORT_PREFIX = textwrap.dedent(
    """
    Role: E-commerce support assistant.
    Constraints: Be concise, policy-compliant, and explicit about next steps. Do not disclose internal data.
    Escalate: duplicate charges, account access without verification, high-value disputes, and refunds outside the window.
    Output shape: customer_message, resolution_type, escalate, internal_tags.
    Tool contract: tool definitions are stable across requests; restrict callable tools with tool_choice.allowed_tools.
    Version: support-agent-optimization-v1.
    """
).strip()
