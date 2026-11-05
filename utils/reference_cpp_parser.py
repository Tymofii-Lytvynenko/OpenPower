"""Extract method bodies from the local reference source for audit evidence."""

import re
from collections.abc import Iterator
from typing import Any


def mask_cpp_noncode(text: str) -> str:
    """Mask comments and literals while preserving source offsets and line breaks."""
    result = list(text)
    index = 0
    while index < len(text):
        start = index
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = len(text) if end < 0 else end + 2
        elif text.startswith('R"', index):
            opening = text.find("(", index + 2, min(len(text), index + 19))
            delimiter = text[index + 2:opening] if opening >= 0 else ""
            if opening < 0 or any(char.isspace() or char in "()\\" for char in delimiter):
                index += 1
                continue
            closing = text.find(")" + delimiter + '"', opening + 1)
            end = len(text) if closing < 0 else closing + len(delimiter) + 2
        elif (text[index] == "'" and index > 0 and index + 1 < len(text)
              and text[index - 1].isalnum() and text[index + 1].isalnum()):
            # C++ digit separators are not character literal delimiters.
            index += 1
            continue
        elif text[index] in {'"', "'"}:
            quote = text[index]
            end = index + 1
            while end < len(text):
                if text[end] == "\\":
                    end += 2
                elif text[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            end = min(end, len(text))
        else:
            index += 1
            continue
        for position in range(start, end):
            if text[position] not in "\r\n":
                result[position] = " "
        index = end
    return "".join(result)


def find_matching(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = start
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'"}:
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def cpp_functions(text: str) -> Iterator[dict[str, Any]]:
    header = re.compile(
        r"(?m)^\s*[\w:<>,*&\s]+?\s+(?P<class>[A-Za-z_]\w*)::(?P<method>[A-Za-z_]\w*)\s*\("
    )
    for match in header.finditer(text):
        open_paren = text.find("(", match.start())
        close_paren = find_matching(text, open_paren, "(", ")")
        if close_paren < 0:
            continue
        open_brace = text.find("{", close_paren + 1)
        semicolon = text.find(";", close_paren + 1)
        if open_brace < 0 or (semicolon >= 0 and semicolon < open_brace):
            continue
        close_brace = find_matching(text, open_brace, "{", "}")
        if close_brace < 0:
            continue
        yield {
            "class": match.group("class"),
            "method": match.group("method"),
            "start": match.start(),
            "line": text.count("\n", 0, match.start()) + 1,
            "body_line": text.count("\n", 0, open_brace + 1) + 1,
            "body": text[open_brace + 1:close_brace],
        }
