"""Runtime value types and helpers for displaying / comparing them.

Decaf values map onto Python values:

    int, float      -> number
    str             -> string
    bool            -> bool
    None            -> nil
    list            -> list (mutable)
    dict            -> dict (mutable)
    Quotation       -> quote (a code block closed over its environment)
    Function        -> user-defined function reference
    BuiltinRef      -> builtin word reference
"""


class Env:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


class Quotation:
    __slots__ = ("code", "env")

    def __init__(self, code, env):
        self.code = code
        self.env = env


class Function:
    __slots__ = ("name", "code", "pos")

    def __init__(self, name, code, pos):
        self.name = name
        self.code = code
        self.pos = pos


class BuiltinRef:
    __slots__ = ("name", "fn")

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn


def type_name(v):
    t = type(v)
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is str:
        return "string"
    if v is None:
        return "nil"
    if t is list:
        return "list"
    if t is dict:
        return "dict"
    if t is Quotation:
        return "quote"
    if t is Function or t is BuiltinRef:
        return "function"
    return t.__name__


def is_callable(v):
    t = type(v)
    return t is Quotation or t is Function or t is BuiltinRef


def truthy(v):
    if v is None or v is False:
        return False
    if v is True:
        return True
    t = type(v)
    if t is int or t is float:
        return v != 0
    if t is str or t is list or t is dict:
        return len(v) > 0
    return True


def format_float(f):
    if f != f:
        return "nan"
    if f == float("inf"):
        return "inf"
    if f == float("-inf"):
        return "-inf"
    return repr(f)


def quote_string(s):
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif ord(c) < 32:
            out.append(f"\\u{{{ord(c):x}}}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def show(v, top=True):
    """Convert a value to its display string.

    At the top level strings are shown raw; nested inside containers (or with
    top=False) they are quoted.
    """
    t = type(v)
    if t is str:
        return v if top else quote_string(v)
    if t is bool:
        return "true" if v else "false"
    if t is int:
        return str(v)
    if t is float:
        return format_float(v)
    if v is None:
        return "nil"
    if t is list:
        return "{ " + " ".join(show(x, False) for x in v) + " }" if v else "{ }"
    if t is dict:
        if not v:
            return "dict{ }"
        return "dict{ " + " ".join(f"{show(k, False)}: {show(x, False)}" for k, x in v.items()) + " }"
    if t is Quotation:
        return "[quote]"
    if t is Function:
        return f"&{v.name}"
    if t is BuiltinRef:
        return f"&{v.name}"
    return repr(v)


def values_equal(a, b):
    ta, tb = type(a), type(b)
    if ta is bool or tb is bool:
        return ta is tb and a == b
    if ta in (int, float) and tb in (int, float):
        return a == b
    if ta is not tb:
        return False
    if ta is list:
        return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))
    if ta is dict:
        if a.keys() != b.keys():
            return False
        return all(values_equal(a[k], b[k]) for k in a)
    if ta is Function or ta is BuiltinRef:
        return a.name == b.name
    if ta is Quotation:
        return a is b
    return a == b
