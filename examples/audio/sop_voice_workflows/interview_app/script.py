"""Questions and status messages for the availability interview."""

CHOICES = {"day": ("Monday", "Tuesday"), "shift": ("morning", "afternoon", "either")}
QUESTIONS = {
    "day": "Which start day works for you, Monday or Tuesday?",
    "shift": "Which shift do you prefer, morning or afternoon?",
}
CONDITIONAL = {
    "day": "Which start day can you choose without that condition, Monday or Tuesday?",
    "shift": "Which shift can you choose without that condition, morning or afternoon?",
}
DEFERRED = "Okay, I'll leave that choice unconfirmed."
STILL_PENDING = "That choice is still unconfirmed. You can tell me when the requirement is met or if another option works."
INTRO = "Hi, this is Alex from Acme Logistics for your availability check. "
SCOPE = "This interview records scheduling availability only. "
FOLLOW_UP = " The recruiting team will need to follow up."
COMPLETED = "Your availability interview is complete. Thank you and goodbye."
CANCELLED = "The availability interview has been cancelled. Goodbye."
STOPPED = "I have stopped your availability interview. It was not submitted as complete. Goodbye."
ASK_CANCEL = "Do you want me to stop and cancel this availability interview?"
AMEND = "Which would you like to change, your start day or your preferred shift?"
CLARIFY = "Which of your availability details needs clarification, your start day or your preferred shift?"
UNKNOWN = "I cannot verify whether that operation went through." + FOLLOW_UP
INTERPRET_FAILED = "I could not verify your response." + FOLLOW_UP
LOOKUP_FAILED = "I couldn't retrieve the next question, so we'll pause here."
CANCEL_FAILED = "I could not confirm cancellation of the interview."
COMPLETE_FAILED = "I could not confirm completion of the interview."


def lookup_failed(saved_value=None):
    if saved_value == "either":
        saved_value = "your availability for either shift"
    return (f"I've saved {saved_value}. " if saved_value else "") + LOOKUP_FAILED


def save_failed(field):
    return f"I could not confirm saving your {field} preference."


def pending_question(field, choice, quote=""):
    target = "your start day" if field == "day" else "your shift preference"
    if choice:
        target = (
            choice
            if field == "day"
            else ("either shift" if choice == "either" else f"the {choice} shift")
        )
    heard = f"You mentioned “{quote}”. " if quote else ""
    return (
        heard
        + f"I can't verify that requirement here. Would you like to leave {target} unconfirmed for now?"
    )


def summary(day, shift):
    shift_detail = (
        "either shift works for you" if shift == "either" else f"your preferred shift is {shift}"
    )
    return (
        f"Your start day is {day} and {shift_detail}. "
        "This records your availability and does not confirm a job offer. Do you confirm both choices?"
    )


def scope_detail(line):
    # Repeated scope questions do not add more prefixes or repeat the introduction.
    return SCOPE + line.removeprefix(SCOPE).removeprefix(INTRO)
