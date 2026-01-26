import json
import re
from typing import Any, Dict, List


def parse_json_dict(json_text: str) -> Dict[str, Any]:
    if not json_text:
        return {}
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower().strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_address(address: str) -> str:
    normalized = normalize_text(address)
    tokens = normalized.split()
    substitutions = {
        "st": "street",
        "ave": "avenue",
        "blvd": "boulevard",
        "rd": "road",
        "dr": "drive",
        "ln": "lane",
        "ct": "court",
        "tx": "texas",
        "ca": "california",
        "ny": "new york",
    }
    expanded_tokens = []
    for token in tokens:
        expanded_tokens.append(substitutions.get(token, token))
    return " ".join(expanded_tokens).strip()


def normalize_order_id(order_id: str) -> str:
    return normalize_text(order_id).replace(" ", "")


def expected_args_subset(expected_args: Dict[str, Any], actual_args: Dict[str, Any]) -> bool:
    for key, expected_value in expected_args.items():
        if key not in actual_args:
            return False
        actual_value = actual_args.get(key)
        if key == "new_address":
            if normalize_address(str(expected_value)) != normalize_address(str(actual_value)):
                return False
        elif key == "order_id":
            if normalize_order_id(str(expected_value)) != normalize_order_id(str(actual_value)):
                return False
        else:
            if normalize_text(str(expected_value)) != normalize_text(str(actual_value)):
                return False
    return True


def compute_tool_call_grade(
    expected_tool_name: str,
    expected_tool_args_text: str,
    tool_calls: List[Dict[str, Any]],
) -> Dict[str, Any]:
    expected_tool_name = expected_tool_name.strip()
    expected_args = parse_json_dict(expected_tool_args_text.strip())

    if not expected_tool_name:
        if not tool_calls:
            return {
                "tool_call_correctness": 1,
                "tool_call_arg_correctness": 1,
                "pred_tool_call": "",
                "pred_tool_call_arg": "",
            }
        first_call = tool_calls[0]
        return {
            "tool_call_correctness": 0,
            "tool_call_arg_correctness": 0,
            "pred_tool_call": first_call.get("name", ""),
            "pred_tool_call_arg": json.dumps(first_call.get("arguments", {})),
        }

    matching_call = None
    for call in tool_calls:
        if call.get("name") == expected_tool_name:
            matching_call = call
            break

    if not matching_call:
        first_call = tool_calls[0] if tool_calls else {}
        return {
            "tool_call_correctness": 0,
            "tool_call_arg_correctness": 0,
            "pred_tool_call": first_call.get("name", ""),
            "pred_tool_call_arg": json.dumps(first_call.get("arguments", {})),
        }

    actual_args = matching_call.get("arguments", {})
    if expected_args:
        args_match = 1 if expected_args_subset(expected_args, actual_args) else 0
    else:
        args_match = 1

    return {
        "tool_call_correctness": 1,
        "tool_call_arg_correctness": args_match,
        "pred_tool_call": matching_call.get("name", ""),
        "pred_tool_call_arg": json.dumps(actual_args),
    }
