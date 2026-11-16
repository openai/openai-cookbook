"""Select interviewer captions for the current ATS summary."""


def summary_captions(captions, release_index, acknowledgement):
    if acknowledgement is None:
        return []
    # A frame that straddles the acknowledgement might belong to the previous question.
    end_ms = acknowledgement["end_ms"]
    return [
        frame
        for frame in captions[release_index:]
        if isinstance(frame.get("start_ms"), int) and frame["start_ms"] >= end_ms
    ]
