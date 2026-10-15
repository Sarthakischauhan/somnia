"""tiktoken-backed token counting. The encoding is configured, never guessed."""

from typing import Literal

import tiktoken

TokenEncoding = Literal["o200k_base", "cl100k_base", "p50k_base", "r50k_base"]


class TiktokenCounter:
    def __init__(self, encoding: TokenEncoding) -> None:
        self.encoding_name: TokenEncoding = encoding
        self._encoding = tiktoken.get_encoding(encoding)

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))
