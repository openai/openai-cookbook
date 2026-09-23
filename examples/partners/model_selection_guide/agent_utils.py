from __future__ import annotations
import json, time, uuid, logging, re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List
from openai import OpenAI

# --- tool back‑ends -------------------------
from tools import chem_lookup, cost_estimator, outcome_db, literature_search, list_available_chemicals

# ---------- tiny infrastructure helpers --------------------------------------

# Holds run-specific parameters provided by user.
@dataclass
class Context:
    compound: str
    goal: str
    budget: float
    time_h: int
    previous: str
    client: OpenAI
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def prompt_vars(self):
        return {
            "compound": self.compound,
            "goal": self.goal,
            "budget": self.budget,
            "time_h": self.time_h,
            "previous": self.previous,
        }

# -- Function‑calling tool manifest --------------------

def load_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "chem_lookup",
                "description": "Mock function to look up chemical properties.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chemical_name": {
                            "type": "string",
                            "description": "The name of the chemical to look up."
                        },
                        "property": {
                            "type": "string",
                            "description": "Optional specific property to retrieve (e.g., 'melting_point'). If None, returns all properties."
                        }
                    },
                    "required": ["chemical_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "cost_estimator",
                "description": "Mock function to estimate the cost of reagents and procedures.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reagents": {
                            "type": "array",
                            "description": "List of reagents, where each reagent is a dictionary with 'name', 'amount', and 'unit'.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Name of the reagent."},
                                    "amount": {"type": "number", "description": "Amount of the reagent."},
                                    "unit": {"type": "string", "description": "Unit for the amount (e.g., 'g', 'mg', 'kg')."}
                                },
                                "required": ["name", "amount", "unit"]
                            }
                        },
                        "equipment": {
                            "type": "array",
                            "description": "Optional list of equipment items used.",
                            "items": {"type": "string"}
                        },
                        "duration_hours": {
                            "type": "number",
                            "description": "Optional duration of the procedure in hours for labor cost calculation."
                        }
                    },
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "outcome_db",
                "description": "Mock function to query the database of past experiment outcomes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "compound": {
                            "type": "string",
                            "description": "The chemical compound name to query past experiments for."
                        },
                        "parameter": {
                            "type": "string",
                            "description": "Optional specific parameter to filter experiments by (e.g., 'yield', 'temperature')."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of experiment results to return (default: 5)."
                        }
                    },
                    "required": ["compound"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "literature_search",
                "description": "Mock function to search scientific literature for relevant information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (keywords) for the literature search."
                        },
                        "filter": {
                            "type": "string",
                            "description": "Optional filter string, potentially including year (e.g., '2023') or journal name."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of search results to return (default: 3)."
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_chemicals",
                "description": "Provides a list of all chemical names available in the database.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    # No parameters needed for this tool
                }
            }
        }
    ]

# -- minimal logger -----------------------------------------------------------

def log_json(stage: str, data: Any, ctx: Context):
    Path("logs").mkdir(exist_ok=True)
    p = Path("logs") / f"{ctx.run_id}.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "stage": stage, "data": data}, indent=2) + "\n")

# -- JSON extractor -----------------------------------------------------

def _parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to rescue JSON from a ```json ...``` block
        m = re.search(r"```(?:json)?\\s*(.*?)```", text, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass          # fall-through to raw
        return {"raw": text}  # give caller *something* parsable


# -- tool call handler --------------------------------------------------------

def _dispatch_tool(name: str, args: Dict[str, Any]):
   """Run the local Python implementation of a tool.
   If the model supplied bad / missing arguments, return an error JSON instead
   of raising – so the conversation can continue."""
   try:
       return {
           "chem_lookup": chem_lookup,
           "cost_estimator": cost_estimator,
           "outcome_db": outcome_db,
           "literature_search": literature_search,
           "list_available_chemicals": list_available_chemicals,
       }[name](**args)
   except TypeError as e:
       # log & surface the problem back to the model in a structured way
       logging.warning(f"Tool {name} failed: {e}")
       return {"tool_error": str(e), "supplied_args": args}

# -- unified OpenAI call w/ recursive tool handling ---------------------------

def call_openai(client: OpenAI, model: str, system: str, user: str, ctx: Context):
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    while True:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=load_tools(),
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_unset=True))
        if not msg.tool_calls:
            log_json(model, msg.content, ctx)
            return _parse_json(msg.content)
        # handle first tool call, then loop again
        for tc in msg.tool_calls:
            result = _dispatch_tool(tc.function.name, json.loads(tc.function.arguments))
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(result)
            })

