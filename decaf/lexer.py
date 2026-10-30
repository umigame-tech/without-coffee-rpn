"""Tokenizer for Decaf source code.

Tokens are separated by whitespace. The characters `[ ] { } | ;` are
self-delimiting, string literals are enclosed in double quotes and `#`
starts a comment that runs to the end of the line.
"""

import re

from .errors import ParseError, SourcePos

DELIMITERS = set("[]{}|;")

INT_RE = re.compile(r"^[+-]?(\d+|0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+)$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")

ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "e": "\x1b",
    "\\": "\\",
    '"': '"',
    "'": "'",
}

# Token kinds
NUM = "num"
STR = "str"
WORD = "word"


class Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind, value, pos):
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, {self.pos})"


def parse_number(text):
    """Return an int/float if `text` is a numeric literal, otherwise None."""
    if INT_RE.match(text):
        sign = -1 if text.startswith("-") else 1
        body = text.lstrip("+-")
        if body[:2].lower() in ("0x", "0b", "0o"):
            return sign * int(body, 0)
        return sign * int(body, 10)
    if FLOAT_RE.match(text):
        return float(text)
    return None


def tokenize(src, filename="<input>"):
    tokens = []
    i = 0
    n = len(src)
    line = 1
    col = 1

    while i < n:
        c = src[i]
        if c == "\n":
            i += 1
            line += 1
            col = 1
            continue
        if c.isspace():
            i += 1
            col += 1
            continue
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue

        pos = SourcePos(filename, line, col)

        # Stack-effect comment: "( a b -- c )". The "(" must stand alone.
        if c == "(" and (i + 1 >= n or src[i + 1].isspace()):
            depth = 0
            end = -1
            for k in range(i, n):
                if src[k] == "(":
                    depth += 1
                elif src[k] == ")":
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end == -1:
                raise ParseError("unterminated '( ... )' comment", pos, incomplete=True)
            for ch in src[i:end + 1]:
                if ch == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
            i = end + 1
            continue

        if c == '"':
            i += 1
            col += 1
            buf = []
            while True:
                if i >= n:
                    raise ParseError("unterminated string literal", pos, incomplete=True)
                c = src[i]
                if c == '"':
                    i += 1
                    col += 1
                    break
                if c == "\\":
                    if i + 1 >= n:
                        raise ParseError("unterminated string literal", pos, incomplete=True)
                    e = src[i + 1]
                    if e in ESCAPES:
                        buf.append(ESCAPES[e])
                        i += 2
                        col += 2
                    elif e == "u" and i + 2 < n and src[i + 2] == "{":
                        end = src.find("}", i + 3)
                        if end == -1:
                            raise ParseError("bad \\u{...} escape", SourcePos(filename, line, col))
                        try:
                            buf.append(chr(int(src[i + 3 : end], 16)))
                        except ValueError:
                            raise ParseError("bad \\u{...} escape", SourcePos(filename, line, col))
                        col += end + 1 - i
                        i = end + 1
                    elif e == "\n":
                        # backslash-newline: line continuation inside a string
                        i += 2
                        line += 1
                        col = 1
                    else:
                        raise ParseError(f"unknown escape sequence '\\{e}'", SourcePos(filename, line, col))
                    continue
                if c == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                buf.append(c)
                i += 1
            tokens.append(Token(STR, "".join(buf), pos))
            continue

        if c in DELIMITERS:
            tokens.append(Token(WORD, c, pos))
            i += 1
            col += 1
            continue

        start = i
        while i < n and not src[i].isspace() and src[i] not in DELIMITERS and src[i] != '"':
            i += 1
        text = src[start:i]
        col += i - start
        num = parse_number(text)
        if num is not None:
            tokens.append(Token(NUM, num, pos))
        else:
            tokens.append(Token(WORD, text, pos))

    return tokens
