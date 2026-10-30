"""Compiles a token stream into flat instruction lists.

An instruction is a tuple `(op, arg, pos)`. Nested blocks (quotations and
list literals) carry their own instruction lists as `arg`.
"""

from .errors import ParseError
from .lexer import NUM, STR, WORD, parse_number

# Opcodes
PUSH = 0      # push a constant
BUILTIN = 1   # call a builtin (arg is the Python function)
WORD_ = 2     # look up a variable or user-defined function at runtime
QUOTE = 3     # push a quotation (closure) over the current environment
LIST = 4      # evaluate a block on a fresh region of the stack, collect as list
SET = 5       # pop into a local variable
SETG = 6      # pop into a global variable
BIND = 7      # pop several values into local variables
FREF = 8      # push a reference to a named function

RESERVED = {":", ";", "[", "]", "{", "}", "|", "->", "=>", "true", "false", "nil"}

CONSTANTS = {"true": True, "false": False, "nil": None}


class FunctionDef:
    __slots__ = ("name", "code", "pos")

    def __init__(self, name, code, pos):
        self.name = name
        self.code = code
        self.pos = pos


class Program:
    __slots__ = ("code", "defs")

    def __init__(self, code, defs):
        self.code = code
        self.defs = defs


class Parser:
    def __init__(self, tokens, builtins):
        self.tokens = tokens
        self.builtins = builtins
        self.i = 0
        self.defs = []
        self.def_names = {}

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse_program(self):
        code = self.parse_block(closer=None, top_level=True)
        return Program(code, self.defs)

    def check_name(self, tok, what):
        if tok is None:
            raise ParseError(f"expected {what} name", incomplete=True)
        if tok.kind != WORD:
            raise ParseError(f"invalid {what} name {tok.value!r}", tok.pos)
        name = tok.value
        if name in RESERVED:
            raise ParseError(f"'{name}' is reserved and cannot be used as a {what} name", tok.pos)
        if name in self.builtins:
            raise ParseError(f"'{name}' is a builtin word and cannot be used as a {what} name", tok.pos)
        if name.startswith("&"):
            raise ParseError(f"{what} names must not start with '&'", tok.pos)
        if parse_number(name) is not None:
            raise ParseError(f"invalid {what} name '{name}'", tok.pos)
        return name

    def parse_block(self, closer, top_level=False, opener=None):
        code = []
        while True:
            tok = self.next()
            if tok is None:
                if closer is None:
                    return code
                raise ParseError(
                    f"missing '{closer}' for '{opener.value}' opened at {opener.pos}",
                    opener.pos,
                    incomplete=True,
                )
            pos = tok.pos
            if tok.kind in (NUM, STR):
                code.append((PUSH, tok.value, pos))
                continue

            w = tok.value
            if w == closer:
                return code
            if w in ("]", "}", ";"):
                raise ParseError(f"unexpected '{w}'", pos)

            if w == "[":
                body = self.parse_block("]", opener=tok)
                code.append((QUOTE, body, pos))
            elif w == "{":
                body = self.parse_block("}", opener=tok)
                code.append((LIST, body, pos))
            elif w == ":":
                if not top_level:
                    raise ParseError("function definitions are only allowed at the top level", pos)
                name = self.check_name(self.next(), "function")
                if name in self.def_names:
                    raise ParseError(
                        f"function '{name}' is already defined at {self.def_names[name]}", pos
                    )
                self.def_names[name] = pos
                body = self.parse_block(";", opener=tok)
                self.defs.append(FunctionDef(name, body, pos))
            elif w == "|":
                names = []
                while True:
                    t = self.next()
                    if t is None:
                        raise ParseError("missing closing '|' for local bindings", pos, incomplete=True)
                    if t.kind == WORD and t.value == "|":
                        break
                    names.append(self.check_name(t, "variable"))
                if len(set(names)) != len(names):
                    raise ParseError("duplicate name in local bindings", pos)
                code.append((BIND, tuple(names), pos))
            elif w == "->":
                code.append((SET, self.check_name(self.next(), "variable"), pos))
            elif w == "=>":
                code.append((SETG, self.check_name(self.next(), "variable"), pos))
            elif w in CONSTANTS:
                code.append((PUSH, CONSTANTS[w], pos))
            elif w.startswith("&") and len(w) > 1:
                code.append((FREF, w[1:], pos))
            elif w in self.builtins:
                code.append((BUILTIN, self.builtins[w], pos))
            else:
                code.append((WORD_, w, pos))


def parse(tokens, builtins):
    return Parser(tokens, builtins).parse_program()
