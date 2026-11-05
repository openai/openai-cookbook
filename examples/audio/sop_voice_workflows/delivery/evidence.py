"""Match evidence on complete words and numbers, allowing case and whitespace differences."""

import re


def contains_quote(source, quote):
    if not isinstance(quote, str) or not any(char.isalnum() for char in quote):
        return False

    def tokens(text):
        words = re.findall(r"\d+(?:[.,]\d+)*|\w+|[^\w\s]", text.casefold().replace("’", "'"))
        return " " + " ".join(words) + " "

    return tokens(quote) in tokens(source)
