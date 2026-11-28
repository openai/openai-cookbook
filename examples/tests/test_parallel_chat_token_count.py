"""Offline regression for literal special-token spellings inside chat messages."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

import tiktoken

count_tokens = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "api_request_parallel_processor.py")
)["num_tokens_consumed_from_request"]


class ChatTokenCountTest(unittest.TestCase):
    def check_content(self, content):
        marker = "<|endoftext|>"
        encoding = tiktoken.Encoding(
            name="local-test", pat_str=r"(?s:.)",
            mergeable_ranks={bytes([n]): n for n in range(256)},
            special_tokens={marker: 256},
        )
        request = {"messages": [{"role": "user", "content": content}], "max_tokens": 7}
        with patch.object(tiktoken, "get_encoding", return_value=encoding):
            count = count_tokens(request, "chat/completions", "local-test")
        # Four message overhead tokens, two reply priming tokens and seven reserved.
        self.assertEqual(count, 4 + len(b"user") + len(content.encode()) + 2 + 7)

    def test_marker_in_documentation_excerpt(self):
        self.check_content("Explain the literal <|endoftext|> in this excerpt.")

    def test_plain_unicode_control(self):
        self.check_content("Pilihan café hitam")
