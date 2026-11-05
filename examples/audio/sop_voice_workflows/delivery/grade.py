"""Grade model tool proposals, store side effects, and factual guidance independently.

The case oracle is read here, after the call. It is never part of a model request.
Wording checks refer to backend guidance. They make no claim about audible speech.
"""

from __future__ import annotations

from collections import Counter
import re

from . import credit_grade

WRITES = {"register_credit", "create_replacement"}
ORDER = "get_order"
CREDIT = "check_credit_eligibility"
STOCK = "check_replacement_availability"


def normalized(value):
    return str(value).casefold().replace("’", "'").replace("–", "-").replace("—", " ").strip()


def has(text, pattern):
    return bool(re.search(pattern, text, flags=re.I))


def asks(text):
    return "?" in text or has(
        text,
        r"\b(ask|check with|please confirm|let me know|would you|shall (i|we)|do you (want|agree|approve)|please tell me)\b",
    )


SUPPORT = r"\b(support|customer (care|service)|service (team|desk)|support team|human agent|our team|speak (to|with) (an? )?(agent|representative))\b"
NO_CHARGE = r"\b(free|complimentary|no (additional |extra |added )?(cost|charge|fee)|(?:at|for) zero (cost|charge|dollars)|without (an? |any )?(additional |extra )?(cost|charge)|won't (?:cost|charge)|no payment|\$0(?:\.00)?\b|zero dollars)\b"
ORIGINAL_ADDRESS = r"(?:original|same|existing|current|order(?:'s)?|on[- ]file).{0,34}(?:address|location)|(?:address|location).{0,40}(?:on (?:the |your )?order|original|on file|originally|you (?:used|provided|gave)|first shipment)"
IN_TRANSIT = r"\b(in transit|on (?:its|the) way|en route|still (?:with the carrier|being shipped|moving)|with the carrier|on the way)\b"
UNSURE = r"can(?:not|'t)|could(?: not|n't)|unable|unavailable|unconfirmed|uncertain|unknown|not (?:yet )?(?:sure|confirmed|clear|available|verified|complete|processed|issued|registered)|no (?:confirmation|update)|(?:did not|didn't|hasn't|haven't|wasn't|not able to)|could.{0,12}not"
READ_FAILURE = (
    UNSURE + r"|fail|error|trouble|issue|problem|couldn't access|went wrong|did not go through"
)
ACTION_NEGATION = (
    UNSURE
    + r"|\b(?:not|never)\b|\bif\b|\bwhether\b|\bwithout\b|don't|won't|not going to|no replacement (?:has|was|is)|no credit (?:has|was|is)"
)
# “$20, sent to your card” describes the offer terms. “Your credit was sent”
# and “I sent the refund” assert an action.
CREDIT_SUCCESS = r"(?:\bcredit|\brefund).{0,45}(?:registered|credited|issued|submitted|processed|applied|posted|on (?:its|the) way|successfully)|(?:\bcredit|\brefund).{0,30}\b(?:was|has been|is now) (?:already )?sent\b|\b(?:issued|registered|applied|submitted|processed|posted|credited|sent)\b.{0,45}\b(?:credit|refund|\$?20|12\.50)|\b(?:credited|refunded)\b|\bRF[- #]?\d+\b"
REPLACEMENT_SUCCESS = r"(?:\breplacement|\breorder|\bnew (?:desk )?lamp).{0,45}(?:created|ordered|placed|registered|submitted|processed|confirmed|arranged|has been sent|on (?:its|the) way|will (?:go|be sent|ship))|(?:created|ordered|placed|put in|submitted|arranged|confirmed|requested|booked|set up)\b.{0,45}\breplacement|\bRP[- #]?\d+\b"


def positive_claim(text, pattern):
    if pattern == REPLACEMENT_SUCCESS:
        # “A replacement can be arranged” describes a possibility. Mask only the
        # prospective verb phrase; another clause can still assert an actual write.
        text = re.sub(
            r"\b(?:can|could|may|might|would|should) (?:then |later )?be "
            r"(?:arranged|created|ordered|placed|registered|submitted|processed|confirmed)\b",
            "",
            text,
        )
    for clause in re.split(r"[.;!?]|\bbut\b|\bhowever\b", text):
        for match in re.finditer(pattern, clause, re.I):
            # A caveat about a separate detail after a supported claim is legitimate.
            # Prefix qualifiers such as "cannot confirm whether" change the claim itself.
            context = clause[: match.end()]
            if not has(context, ACTION_NEGATION):
                return True
    return False


def proposed_references(text):
    digits = {
        "zero": "0",
        "oh": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    word = "(?:" + "|".join(digits) + ")"
    pattern = r"\br[\s-]?([pf])[#:\s-]*(\d(?:[ -]?\d){2,}|" + word + "(?:[ -]+" + word + r"){2,})\b"
    refs = set()
    for letter, suffix in re.findall(pattern, normalized(text)):
        numbers = (
            "".join(digits[x] for x in re.split("[ -]+", suffix))
            if suffix[0].isalpha()
            else re.sub(r"\D", "", suffix)
        )
        refs.add("R" + letter.upper() + numbers)
    return refs


def check_guidance(rule, event):
    text = normalized(event.get("reply", ""))
    kind, ref = event.get("offer_kind"), event.get("offer_ref")
    if rule == "replacement_offer":
        terms = [
            ("current offer metadata", (kind, ref) == ("replacement", "REPL-LAMP-1")),
            (
                "replacement lamp",
                has(text, r"\blamp\b")
                and has(text, r"replac|new (?:desk )?lamp|same (?:item|(?:desk )?lamp)"),
            ),
            ("no charge", has(text, NO_CHARGE)),
            ("original order address", has(text, ORIGINAL_ADDRESS)),
            ("permission question", asks(text)),
        ]
    else:
        checks = {
            "ask_damage": asks(text)
            and has(
                text,
                r"what.{0,40}(part|damage|broke|broken|crack|happen|wrong)|which.{0,30}(part|piece|area)|(?:describe|tell|share|explain|detail|more|nature|kind|type).{0,45}(damage|broken|crack|broke|issue|problem|happen|wrong|wrong with)|how.{0,25}(broken|damaged|broke)|more (?:details?|specific)",
            ),
            "replacement_confirmed": positive_claim(text, REPLACEMENT_SUCCESS),
            "credit_confirmed": positive_claim(text, CREDIT_SUCCESS),
            "in_transit": positive_claim(text, IN_TRANSIT),
            "no_invented_eta": not positive_claim(
                text,
                r"(?:arrive|deliver|expect|due|scheduled).{0,35}(?:today|tomorrow|(?:mon|tues|wednes|thurs|fri|satur|sun)day|next week|\b\d{1,2} (?:business )?(?:days?|hours?)\b|\b\d{1,2}/\d{1,2}\b)",
            ),
            "credit_ineligible": has(
                text,
                r"not (?:eligible|available|qualif)|does(?:n't| not) qualif|(?:cannot|can't|unable to|do not|don't|won't).{0,35}(?:credit|refund|apply|issue)|ineligible|(?:only|requires?|must|need|more than|over|exceed).{0,38}(?:24|twenty.four)",
            ),
            "out_of_stock": has(
                text,
                r"out of stock|not (?:currently )?(?:in stock|available)|no (?:longer |current )?stock|unavailable|don't have .{0,25}(?:stock|another)|isn't (?:in stock|available)",
            ),
            "delivery_conflict": has(
                text,
                IN_TRANSIT
                + r"|(?:can't|cannot|couldn't|unable|not|no).{0,35}(?:delivered|delivery|confirmed)|(?:delivery|shipment).{0,28}(?:unverified|confirmed yet|not (?:yet )?(?:verified|confirmed))",
            ),
            "support": has(text, SUPPORT),
            "read_failure": has(text, READ_FAILURE),
            "uncertain": has(text, UNSURE),
            "no_credit_claim": not positive_claim(text, CREDIT_SUCCESS),
            "no_replacement_claim": not positive_claim(text, REPLACEMENT_SUCCESS),
            "no_tracking_claim": not positive_claim(
                text, IN_TRANSIT + r"|(?:was|has been|marked|is) delivered"
            ),
            "address_limit": has(text, ORIGINAL_ADDRESS)
            or has(
                text,
                r"(?:can't|cannot|unable|not able|don't|only).{0,38}(?:office|address|different|change)",
            ),
        }
        if rule not in checks:
            raise ValueError(f"Unknown guidance rubric {rule}")
        terms = [(rule, checks[rule])]
    return [label for label, passed in terms if not passed]


def grade(case, trace):
    problems = {key: [] for key in ("routing", "tool_results", "effects", "guidance", "race")}
    needs_review = []
    events = trace.get("events", [])
    spec = case["expect"]
    events_by_name = {}
    requirements = {r["name"]: r for r in spec["tools"]}
    stale_expected = bool(case.get("delay_first_read"))
    for event in events:
        if event.get("type") == "consent_review" and event.get("decision") == "unavailable":
            problems["tool_results"].append(f"turn {event['turn']}: no usable consent decision")
        if event.get("type") != "tool":
            continue
        name, turn = event.get("name"), event.get("turn")
        status = event.get("result", {}).get("status")
        if stale_expected and name == ORDER and status == "stale":
            continue
        events_by_name.setdefault(name, []).append(event)
        rule = requirements.get(name)
        if rule is None:
            problems["routing"].append(f"turn {turn}: unexpected proposal {name}")
            continue
        allowed = rule["turns"]
        repeated_read = (
            name not in WRITES
            and turn > min(allowed)
            and (
                name == ORDER
                or not any(other in requirements and other != name for other in (CREDIT, STOCK))
            )
        )
        if turn not in allowed and not repeated_read:
            problems["routing"].append(f"turn {turn}: {name} outside required step {allowed}")
        if status != rule["status"]:
            problems["tool_results"].append(
                f"turn {turn}: {name} returned {status}, expected {rule['status']}"
            )
        for arg, expected in rule["fields"].items():
            if event.get("args", {}).get(arg) != expected:
                problems["routing"].append(f"turn {turn}: {name}.{arg} must be {expected}")
        for arg, patterns in rule["words"].items():
            supplied = normalized(event.get("args", {}).get(arg, ""))
            if not all(has(supplied, pattern) for pattern in patterns):
                problems["routing"].append(
                    f"turn {turn}: {name}.{arg} misses caller detail ({', '.join(patterns)})"
                )

    for rule in spec["tools"]:
        name = rule["name"]
        matching = events_by_name.get(name, [])
        if not rule["optional"] and not any(e["turn"] in rule["turns"] for e in matching):
            problems["routing"].append(f"turn {rule['turns']}: missing required {name}")
        if name in WRITES and len(matching) > 1:
            problems["routing"].append(f"{name} proposed {len(matching)} times for one acceptance")
    # Inspect event order in addition to turn numbers. A rejected premature lookup on the same
    # turn cannot pass because a later call eventually succeeded.
    tool_order = [
        e["name"]
        for e in events
        if e.get("type") == "tool" and e.get("result", {}).get("status") != "stale"
    ]
    for name in (CREDIT, STOCK):
        if name in tool_order and (
            ORDER not in tool_order or tool_order.index(ORDER) > tool_order.index(name)
        ):
            problems["routing"].append(f"{name} proposed before a current order lookup")
    expected_effects = Counter((e["kind"], e["ref"]) for e in spec["effects"])
    observed_effects = Counter((e.get("kind"), e.get("ref")) for e in trace.get("effects", []))
    if observed_effects != expected_effects:
        problems["effects"].append(
            f"merchant ledger {dict(observed_effects)}; expected {dict(expected_effects)}"
        )

    if stale_expected:
        withheld = [e for e in events if e.get("type") == "withheld"]
        dropped = [e for e in events if e.get("type") == "stale_drop"]
        if (
            len(withheld) != 1
            or withheld[0].get("name", ORDER) != ORDER
            or withheld[0].get("turn") != 1
        ):
            problems["race"].append("missing the first withheld tracking read")
        if len(dropped) != 1 or dropped[0].get("name", ORDER) != ORDER:
            problems["race"].append("missing the stale tracking result drop")
        if withheld and dropped and events.index(dropped[0]) <= events.index(withheld[0]):
            problems["race"].append("stale result logged before the withheld read")
        if any(e.get("type") == "guidance" and e.get("turn") == 1 for e in events):
            problems["race"].append("superseded tracking turn supplied guidance")

    for turn_string, rules in spec["guidance"].items():
        turn = int(turn_string)
        rows = [e for e in events if e.get("type") == "guidance" and e.get("turn") == turn]
        if (
            len(rows) != 1
            or not isinstance(rows[0].get("reply"), str)
            or not rows[0]["reply"].strip()
        ):
            problems["guidance"].append(
                f"turn {turn}: expected one nonempty reply, received {len(rows)}"
            )
            continue
        reply = rows[0]
        credit_rules = [rule for rule in rules if credit_grade.applies(rule)]
        if credit_rules:
            reviews = trace.get("credit_reviews")
            review = reviews.get(turn_string) if isinstance(reviews, dict) else None
            issues, pending = credit_grade.assess(
                credit_rules, reply, events[: events.index(reply)], review
            )
            problems["guidance"].extend(f"turn {turn}: {issue}" for issue in issues)
            needs_review.extend(f"guidance: turn {turn}: {issue}" for issue in pending)
        for rule in rules:
            if not credit_grade.applies(rule):
                for issue in check_guidance(rule, reply):
                    problems["guidance"].append(f"turn {turn}: {rule} / {issue}")
        # Reference spelling and write execution are independent. On the replacement path
        # the SOP also requests the reference be given to the caller.
        references = proposed_references(reply["reply"])
        receipts = set()
        confirmed_kinds = set()
        for e in events[: events.index(reply)]:
            if e.get("type") == "tool":
                result = e.get("result", {})
                for tool_name, field, kind, statuses in (
                    (
                        "register_credit",
                        "refund_id",
                        "credit",
                        {"registered", "already_registered"},
                    ),
                    (
                        "create_replacement",
                        "replacement_id",
                        "replacement",
                        {"created", "already_created"},
                    ),
                ):
                    if (
                        e.get("name") == tool_name
                        and result.get("status") in statuses
                        and result.get(field)
                    ):
                        confirmed_kinds.add(kind)
                        receipts.add(str(result[field]).upper())
        for rule, kind in (
            ("credit_confirmed", "credit"),
            ("replacement_confirmed", "replacement"),
        ):
            if rule in rules and kind not in confirmed_kinds:
                problems["guidance"].append(
                    f"turn {turn}: claimed {kind} success before a confirmed tool receipt"
                )
        if "replacement_confirmed" in rules and not any(
            ref.startswith("RP") and ref in receipts for ref in references
        ):
            problems["guidance"].append(f"turn {turn}: missing verified replacement reference")
        if references - receipts:
            problems["guidance"].append(f"turn {turn}: unsupported receipt reference")
    failures = [f"{dimension}: {x}" for dimension, items in problems.items() for x in items]
    if trace.get("status") == "error":
        failures.append(trace.get("error") or "Backend trace ended in error")
    dimensions = {key: not items for key, items in problems.items()}
    if needs_review and dimensions["guidance"]:
        dimensions["guidance"] = None
    status = "fail" if failures else "review" if needs_review else "pass"
    return {
        "status": status,
        "pass": status == "pass",
        "failures": failures,
        "needs_review": needs_review,
        "dimensions": dimensions,
    }
