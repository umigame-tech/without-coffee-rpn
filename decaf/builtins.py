"""Builtin words.

Every builtin is a Python function taking the interpreter. Most are
registered through `@word(name, arity)`, which pops `arity` arguments
(deepest first), calls the function and pushes its return value.
"""

import math
import os
import random as _rnd
import time as _clock

from .errors import (
    BreakSignal,
    ContinueSignal,
    DecafError,
    ExitSignal,
    ReturnSignal,
)
from .lexer import parse_number
from .values import (
    is_callable,
    show,
    truthy,
    type_name,
    values_equal,
)

BUILTINS = {}
DOCS = {}

NOTHING = object()  # return value meaning "push nothing"


class Many(tuple):
    """Return value meaning "push each of these values"."""


class ArgError(Exception):
    pass


def _wrap(name, fn):
    def call(interp):
        try:
            fn(interp)
        except ArgError as e:
            raise DecafError(f"'{name}': {e}")

    return call


def native(name, effect=""):
    """Register a builtin that manipulates the interpreter directly."""

    def deco(fn):
        BUILTINS[name] = _wrap(name, fn)
        DOCS[name] = effect
        return fn

    return deco


def word(name, arity, effect=""):
    """Register a builtin that pops `arity` values and pushes the result."""

    def deco(fn):
        def call(interp):
            st = interp.stack
            if len(st) < arity:
                raise DecafError(
                    f"stack underflow: '{name}' needs {arity} value{'s' if arity != 1 else ''}, "
                    f"stack has {len(st)}"
                )
            if arity:
                args = st[-arity:]
                del st[-arity:]
            else:
                args = ()
            try:
                r = fn(*args)
            except ArgError as e:
                raise DecafError(f"'{name}': {e}")
            if r is NOTHING:
                return
            if type(r) is Many:
                st.extend(r)
            else:
                st.append(r)

        BUILTINS[name] = call
        DOCS[name] = effect
        return fn

    return deco


def alias(new, old):
    BUILTINS[new] = BUILTINS[old]
    DOCS[new] = DOCS[old]


# ----------------------------------------------------------------------
# Argument checking helpers


def _desc(v):
    return f"{type_name(v)} {show(v, False)}" if type(v) not in (list, dict) else type_name(v)


def num(v):
    t = type(v)
    if t is int or t is float:
        return v
    raise ArgError(f"expected a number, got {_desc(v)}")


def integer(v):
    if type(v) is int:
        return v
    if type(v) is float and v.is_integer():
        return int(v)
    raise ArgError(f"expected an integer, got {_desc(v)}")


def string(v):
    if type(v) is str:
        return v
    raise ArgError(f"expected a string, got {_desc(v)}")


def lst(v):
    if type(v) is list:
        return v
    raise ArgError(f"expected a list, got {_desc(v)}")


def dct(v):
    if type(v) is dict:
        return v
    raise ArgError(f"expected a dict, got {_desc(v)}")


def seq(v):
    if type(v) in (str, list):
        return v
    raise ArgError(f"expected a string or list, got {_desc(v)}")


def callable_(v):
    if is_callable(v):
        return v
    raise ArgError(f"expected a quotation or function, got {_desc(v)}")


def key(v):
    if type(v) in (str, int, float, bool) or v is None:
        return v
    raise ArgError(f"{type_name(v)} cannot be used as a dict key")


def pop_args(interp, name, n):
    st = interp.stack
    if len(st) < n:
        raise DecafError(f"stack underflow: '{name}' needs {n} values, stack has {len(st)}")
    args = st[-n:]
    del st[-n:]
    return args


# ----------------------------------------------------------------------
# Stack manipulation


@word("dup", 1, "( a -- a a )")
def _dup(a):
    return Many((a, a))


@word("drop", 1, "( a -- )")
def _drop(a):
    return NOTHING


@word("swap", 2, "( a b -- b a )")
def _swap(a, b):
    return Many((b, a))


@word("over", 2, "( a b -- a b a )")
def _over(a, b):
    return Many((a, b, a))


@word("rot", 3, "( a b c -- b c a )")
def _rot(a, b, c):
    return Many((b, c, a))


@word("-rot", 3, "( a b c -- c a b )")
def _mrot(a, b, c):
    return Many((c, a, b))


@word("nip", 2, "( a b -- b )")
def _nip(a, b):
    return b


@word("tuck", 2, "( a b -- b a b )")
def _tuck(a, b):
    return Many((b, a, b))


@word("2dup", 2, "( a b -- a b a b )")
def _2dup(a, b):
    return Many((a, b, a, b))


@word("2drop", 2, "( a b -- )")
def _2drop(a, b):
    return NOTHING


@word("2swap", 4, "( a b c d -- c d a b )")
def _2swap(a, b, c, d):
    return Many((c, d, a, b))


@native("pick", "( xn ... x0 n -- xn ... x0 xn )")
def _pick(interp):
    n = integer(interp.pop())
    st = interp.stack
    if n < 0 or n >= len(st):
        raise ArgError(f"index {n} out of range (stack depth {len(st)})")
    st.append(st[-1 - n])


@native("depth", "( -- n )")
def _depth(interp):
    interp.stack.append(len(interp.stack))


@native("clear", "( ... -- )")
def _clear(interp):
    interp.stack.clear()


# ----------------------------------------------------------------------
# Arithmetic


@word("+", 2, "( a b -- a+b )  numbers, strings or lists")
def _add(a, b):
    ta, tb = type(a), type(b)
    if ta is str and tb is str:
        return a + b
    if ta is list and tb is list:
        return a + b
    if ta is str or tb is str:
        raise ArgError(
            f"cannot add {type_name(a)} and {type_name(b)} (use 'str' to convert to a string first)"
        )
    return num(a) + num(b)


@word("-", 2, "( a b -- a-b )")
def _sub(a, b):
    return num(a) - num(b)


@word("*", 2, "( a b -- a*b )  also string/list * int repeats")
def _mul(a, b):
    if type(a) in (str, list):
        return a * integer(b)
    return num(a) * num(b)


@word("/", 2, "( a b -- a/b )  exact for ints that divide evenly, float otherwise")
def _div(a, b):
    a, b = num(a), num(b)
    if b == 0:
        raise ArgError("division by zero")
    if type(a) is int and type(b) is int and a % b == 0:
        return a // b
    return a / b


@word("div", 2, "( a b -- floor(a/b) )  integer division")
def _idiv(a, b):
    a, b = num(a), num(b)
    if b == 0:
        raise ArgError("division by zero")
    r = a // b
    return int(r) if type(r) is float else r


@word("mod", 2, "( a b -- a mod b )")
def _mod(a, b):
    a, b = num(a), num(b)
    if b == 0:
        raise ArgError("division by zero")
    return a % b


alias("%", "mod")


@word("**", 2, "( a b -- a^b )")
def _pow(a, b):
    a, b = num(a), num(b)
    if type(a) is int and type(b) is int and b < 0:
        return float(a) ** b
    return a**b


@word("neg", 1, "( a -- -a )")
def _neg(a):
    return -num(a)


@word("abs", 1, "( a -- |a| )")
def _abs(a):
    return abs(num(a))


@word("inc", 1, "( a -- a+1 )")
def _inc(a):
    return num(a) + 1


@word("dec", 1, "( a -- a-1 )")
def _dec(a):
    return num(a) - 1


@word("min", 2, "( a b -- min )")
def _min(a, b):
    _cmp_check(a, b)
    return b if b < a else a


@word("max", 2, "( a b -- max )")
def _max(a, b):
    _cmp_check(a, b)
    return b if b > a else a


@word("floor", 1, "( x -- int )")
def _floor(a):
    return math.floor(num(a))


@word("ceil", 1, "( x -- int )")
def _ceil(a):
    return math.ceil(num(a))


@word("round", 1, "( x -- int )")
def _round(a):
    return round(num(a))


@word("sqrt", 1, "( x -- sqrt(x) )")
def _sqrt(a):
    a = num(a)
    if a < 0:
        raise ArgError("square root of a negative number")
    r = math.isqrt(a) if type(a) is int else None
    if r is not None and r * r == a:
        return r
    return math.sqrt(a)


def _math1(name, f):
    @word(name, 1, f"( x -- {name}(x) )")
    def _f(a):
        try:
            return f(num(a))
        except ValueError:
            raise ArgError(f"math domain error for {show(a)}")


for _n, _f in [
    ("sin", math.sin),
    ("cos", math.cos),
    ("tan", math.tan),
    ("asin", math.asin),
    ("acos", math.acos),
    ("atan", math.atan),
    ("exp", math.exp),
    ("log", math.log),
    ("log10", math.log10),
]:
    _math1(_n, _f)


@word("atan2", 2, "( y x -- atan2(y,x) )")
def _atan2(y, x):
    return math.atan2(num(y), num(x))


@word("pi", 0, "( -- 3.14159... )")
def _pi():
    return math.pi


@word("bit-and", 2, "( a b -- a&b )")
def _band(a, b):
    return integer(a) & integer(b)


@word("bit-or", 2, "( a b -- a|b )")
def _bor(a, b):
    return integer(a) | integer(b)


@word("bit-xor", 2, "( a b -- a^b )")
def _bxor(a, b):
    return integer(a) ^ integer(b)


@word("shl", 2, "( a n -- a<<n )")
def _shl(a, b):
    return integer(a) << integer(b)


@word("shr", 2, "( a n -- a>>n )")
def _shr(a, b):
    return integer(a) >> integer(b)


# ----------------------------------------------------------------------
# Comparison and logic


def _cmp_check(a, b):
    ta, tb = type(a), type(b)
    if ta in (int, float) and tb in (int, float):
        return
    if ta is str and tb is str:
        return
    raise ArgError(f"cannot compare {type_name(a)} with {type_name(b)}")


@word("=", 2, "( a b -- bool )")
def _eq(a, b):
    return values_equal(a, b)


@word("!=", 2, "( a b -- bool )")
def _ne(a, b):
    return not values_equal(a, b)


@word("<", 2, "( a b -- bool )")
def _lt(a, b):
    _cmp_check(a, b)
    return a < b


@word(">", 2, "( a b -- bool )")
def _gt(a, b):
    _cmp_check(a, b)
    return a > b


@word("<=", 2, "( a b -- bool )")
def _le(a, b):
    _cmp_check(a, b)
    return a <= b


@word(">=", 2, "( a b -- bool )")
def _ge(a, b):
    _cmp_check(a, b)
    return a >= b


@word("and", 2, "( a b -- a|b )  a if a is falsy, otherwise b")
def _and(a, b):
    return b if truthy(a) else a


@word("or", 2, "( a b -- a|b )  a if a is truthy, otherwise b")
def _or(a, b):
    return a if truthy(a) else b


@word("not", 1, "( a -- bool )")
def _not(a):
    return not truthy(a)


# ----------------------------------------------------------------------
# Control flow


@native("call", "( quote -- ... )  run a quotation or function")
def _call(interp):
    interp.call(callable_(interp.pop()))


@native("if", "( cond [then] [else] -- ... )")
def _if(interp):
    cond, then, else_ = pop_args(interp, "if", 3)
    interp.call(callable_(then) if truthy(cond) else callable_(else_))


@native("when", "( cond [then] -- ... )")
def _when(interp):
    cond, then = pop_args(interp, "when", 2)
    callable_(then)
    if truthy(cond):
        interp.call(then)


@native("unless", "( cond [else] -- ... )")
def _unless(interp):
    cond, body = pop_args(interp, "unless", 2)
    callable_(body)
    if not truthy(cond):
        interp.call(body)


@native("cond", "( { [test] [body] ... } -- ... )  run the body of the first true test")
def _cond(interp):
    clauses = lst(interp.pop())
    if len(clauses) % 2:
        raise ArgError("expects an even number of quotations (test/body pairs)")
    for i in range(0, len(clauses), 2):
        interp.call(callable_(clauses[i]))
        if truthy(interp.pop()):
            interp.call(callable_(clauses[i + 1]))
            return


@native("while", "( [cond] [body] -- )  loop while cond leaves a true value")
def _while(interp):
    cond, body = pop_args(interp, "while", 2)
    callable_(cond)
    callable_(body)
    call = interp.call
    while True:
        call(cond)
        if not truthy(interp.pop()):
            break
        try:
            call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("loop", "( [body] -- )  loop forever (until break / return)")
def _loop(interp):
    body = callable_(interp.pop())
    call = interp.call
    while True:
        try:
            call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("times", "( n [body] -- )  run body n times")
def _times(interp):
    n, body = pop_args(interp, "times", 2)
    n = integer(n)
    callable_(body)
    call = interp.call
    for _ in range(n):
        try:
            call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("for", "( start end [body] -- )  body gets i on the stack, start <= i < end")
def _for(interp):
    start, end, body = pop_args(interp, "for", 3)
    start, end = integer(start), integer(end)
    callable_(body)
    call = interp.call
    push = interp.stack.append
    for i in range(start, end):
        push(i)
        try:
            call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("for-step", "( start end step [body] -- )  like for, with a custom step")
def _for_step(interp):
    start, end, step, body = pop_args(interp, "for-step", 4)
    start, end, step = num(start), num(end), num(step)
    if step == 0:
        raise ArgError("step must not be 0")
    callable_(body)
    i = start
    while (i < end) if step > 0 else (i > end):
        interp.stack.append(i)
        try:
            interp.call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass
        i += step


def _iter_items(coll):
    t = type(coll)
    if t is list:
        return list(coll)
    if t is str:
        return list(coll)
    if t is dict:
        return list(coll.items())
    raise ArgError(f"expected a list, string or dict, got {_desc(coll)}")


@native("each", "( coll [body] -- )  body gets each element (dicts: key value)")
def _each(interp):
    coll, body = pop_args(interp, "each", 2)
    callable_(body)
    is_dict = type(coll) is dict
    for item in _iter_items(coll):
        if is_dict:
            interp.stack.extend(item)
        else:
            interp.stack.append(item)
        try:
            interp.call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("each-index", "( list [body] -- )  body gets element and index")
def _each_index(interp):
    coll, body = pop_args(interp, "each-index", 2)
    callable_(body)
    for i, item in enumerate(_iter_items(seq(coll))):
        interp.stack.append(item)
        interp.stack.append(i)
        try:
            interp.call(body)
        except BreakSignal:
            break
        except ContinueSignal:
            pass


@native("break", "( -- )  leave the innermost loop")
def _break(interp):
    raise BreakSignal()


@native("continue", "( -- )  skip to the next iteration")
def _continue(interp):
    raise ContinueSignal()


@native("return", "( -- )  return from the current function")
def _return(interp):
    raise ReturnSignal()


@native("throw", "( value -- )  raise an error")
def _throw(interp):
    v = interp.pop()
    raise DecafError(show(v), value=v)


@native("try", "( [body] [handler] -- )  on error, restore the stack and run handler with the error value")
def _try(interp):
    body, handler = pop_args(interp, "try", 2)
    callable_(body)
    callable_(handler)
    depth = len(interp.stack)
    try:
        interp.call(body)
    except DecafError as e:
        del interp.stack[depth:]
        interp.stack.append(e.value)
        interp.call(handler)


@native("assert", "( cond message -- )  throw message if cond is false")
def _assert(interp):
    cond, msg = pop_args(interp, "assert", 2)
    if not truthy(cond):
        raise DecafError(f"assertion failed: {show(msg)}", value=msg)


@native("exit", "( code -- )  terminate the program")
def _exit(interp):
    raise ExitSignal(integer(interp.pop()))


# ----------------------------------------------------------------------
# Higher-order list operations


@native("map", "( list [f] -- list )")
def _map(interp):
    coll, f = pop_args(interp, "map", 2)
    callable_(f)
    items = _iter_items(seq(coll))
    out = [interp.call_with(f, x) for x in items]
    if type(coll) is str:
        return interp.stack.append("".join(show(x) for x in out))
    interp.stack.append(out)


@native("filter", "( list [pred] -- list )")
def _filter(interp):
    coll, f = pop_args(interp, "filter", 2)
    callable_(f)
    out = [x for x in _iter_items(seq(coll)) if truthy(interp.call_with(f, x))]
    interp.stack.append("".join(out) if type(coll) is str else out)


@native("reduce", "( list init [f] -- result )  f: ( acc x -- acc )")
def _reduce(interp):
    coll, acc, f = pop_args(interp, "reduce", 3)
    callable_(f)
    for x in _iter_items(seq(coll)):
        acc = interp.call_with(f, acc, x)
    interp.stack.append(acc)


@native("find", "( list [pred] -- item|nil )  first element satisfying pred")
def _find(interp):
    coll, f = pop_args(interp, "find", 2)
    callable_(f)
    for x in _iter_items(seq(coll)):
        if truthy(interp.call_with(f, x)):
            interp.stack.append(x)
            return
    interp.stack.append(None)


@native("any?", "( list [pred] -- bool )")
def _any(interp):
    coll, f = pop_args(interp, "any?", 2)
    callable_(f)
    interp.stack.append(any(truthy(interp.call_with(f, x)) for x in _iter_items(seq(coll))))


@native("all?", "( list [pred] -- bool )")
def _all(interp):
    coll, f = pop_args(interp, "all?", 2)
    callable_(f)
    interp.stack.append(all(truthy(interp.call_with(f, x)) for x in _iter_items(seq(coll))))


def _sort_key(v):
    t = type(v)
    if t in (int, float):
        return (0, v, "")
    if t is str:
        return (1, 0, v)
    raise ArgError(f"cannot sort values of type {type_name(v)}")


@word("sort", 1, "( list -- list )  sorted copy (numbers before strings)")
def _sort(coll):
    return sorted(lst(coll), key=_sort_key)


@native("sort-by", "( list [key] -- list )  sorted copy, ordered by key")
def _sort_by(interp):
    coll, f = pop_args(interp, "sort-by", 2)
    callable_(f)
    keyed = [(_sort_key(interp.call_with(f, x)), i, x) for i, x in enumerate(lst(coll))]
    keyed.sort(key=lambda t: (t[0], t[1]))
    interp.stack.append([x for _, _, x in keyed])


# ----------------------------------------------------------------------
# Sequences (strings and lists)


@word("len", 1, "( coll -- n )")
def _len(c):
    if type(c) in (str, list, dict):
        return len(c)
    raise ArgError(f"expected a string, list or dict, got {_desc(c)}")


@word("empty?", 1, "( coll -- bool )")
def _empty(c):
    return _len(c) == 0


def _index(c, i):
    i = integer(i)
    n = len(c)
    if i < -n or i >= n:
        raise ArgError(f"index {i} out of range (length {n})")
    return i


@word("get", 2, "( coll key -- value )  list/string index or dict key (nil if missing)")
def _get(c, k):
    if type(c) is dict:
        return c.get(key(k))
    return seq(c)[_index(c, k)]


@word("put", 3, "( coll key value -- coll )  set list index or dict key (mutates)")
def _put(c, k, v):
    if type(c) is dict:
        c[key(k)] = v
        return c
    lst(c)[_index(c, k)] = v
    return c


@word("del", 2, "( coll key -- coll )  remove list index or dict key (mutates)")
def _del(c, k):
    if type(c) is dict:
        c.pop(key(k), None)
        return c
    del lst(c)[_index(c, k)]
    return c


@word("has?", 2, "( dict key -- bool )")
def _has(c, k):
    return key(k) in dct(c)


@word("contains?", 2, "( coll x -- bool )  substring, list element or dict key")
def _contains(c, x):
    t = type(c)
    if t is str:
        return string(x) in c
    if t is list:
        return any(values_equal(e, x) for e in c)
    if t is dict:
        return key(x) in c
    raise ArgError(f"expected a string, list or dict, got {_desc(c)}")


@word("index-of", 2, "( coll x -- i )  -1 if not found")
def _index_of(c, x):
    if type(c) is str:
        return c.find(string(x))
    for i, e in enumerate(lst(c)):
        if values_equal(e, x):
            return i
    return -1


@word("slice", 3, "( coll start end -- coll )  end exclusive, negatives count from the end")
def _slice(c, s, e):
    seq(c)
    s = integer(s) if s is not None else None
    e = integer(e) if e is not None else None
    return c[s:e]


@word("reverse", 1, "( coll -- coll )  reversed copy")
def _reverse(c):
    return seq(c)[::-1]


@word("first", 1, "( coll -- x )")
def _first(c):
    if not seq(c):
        raise ArgError("empty sequence")
    return c[0]


@word("last", 1, "( coll -- x )")
def _last(c):
    if not seq(c):
        raise ArgError("empty sequence")
    return c[-1]


@word("rest", 1, "( coll -- coll )  all but the first element")
def _rest(c):
    return seq(c)[1:]


@word("push", 2, "( list x -- list )  append (mutates)")
def _push(c, x):
    lst(c).append(x)
    return c


@word("pop", 1, "( list -- list x )  remove the last element (mutates)")
def _pop(c):
    if not lst(c):
        raise ArgError("pop from an empty list")
    x = c.pop()
    return Many((c, x))


@word("insert", 3, "( list i x -- list )  insert before index i (mutates)")
def _insert(c, i, x):
    lst(c).insert(integer(i), x)
    return c


@word("copy", 1, "( coll -- coll )  shallow copy")
def _copy(c):
    if type(c) is list:
        return list(c)
    if type(c) is dict:
        return dict(c)
    return c


@word("range", 2, "( start end -- list )  start <= i < end")
def _range(a, b):
    return list(range(integer(a), integer(b)))


@word("sum", 1, "( list -- n )")
def _sum(c):
    total = 0
    for x in lst(c):
        total += num(x)
    return total


@native("spread", "( list -- x1 x2 ... xn )  push every element")
def _spread(interp):
    interp.stack.extend(lst(interp.pop()))


@native("collect", "( x1 ... xn n -- list )  gather the top n values into a list")
def _collect(interp):
    n = integer(interp.pop())
    if n < 0 or n > len(interp.stack):
        raise ArgError(f"cannot collect {n} values (stack depth {len(interp.stack)})")
    items = interp.stack[len(interp.stack) - n :]
    del interp.stack[len(interp.stack) - n :]
    interp.stack.append(items)


# ----------------------------------------------------------------------
# Dicts


@word("dict", 0, "( -- dict )  new empty dict")
def _dict():
    return {}


@word("keys", 1, "( dict -- list )")
def _keys(d):
    return list(dct(d).keys())


@word("values", 1, "( dict -- list )")
def _values(d):
    return list(dct(d).values())


@word("items", 1, "( dict -- list )  list of { key value } pairs")
def _items(d):
    return [[k, v] for k, v in dct(d).items()]


# ----------------------------------------------------------------------
# Strings


@word("str", 1, "( x -- string )  display form of any value")
def _str(x):
    return show(x)


@word("repr", 1, "( x -- string )  like str, but strings are quoted")
def _repr(x):
    return show(x, False)


@word("num", 1, "( string -- number|nil )  parse a number, nil if invalid")
def _num(s):
    if type(s) in (int, float) and type(s) is not bool:
        return s
    return parse_number(string(s).strip())


@word("int", 1, "( x -- int|nil )  truncate a number or parse a string")
def _int(x):
    t = type(x)
    if t is int:
        return x
    if t is float:
        if x != x or x in (float("inf"), float("-inf")):
            raise ArgError(f"cannot convert {show(x)} to int")
        return int(x)
    if t is bool:
        return 1 if x else 0
    n = parse_number(string(x).strip())
    return None if n is None else int(n)


@word("float", 1, "( x -- float|nil )")
def _float(x):
    t = type(x)
    if t in (int, float) and t is not bool:
        return float(x)
    n = parse_number(string(x).strip())
    if n is None:
        low = x.strip().lower()
        if low in ("inf", "-inf", "nan"):
            return float(low)
        return None
    return float(n)


@word("upper", 1, "( s -- S )")
def _upper(s):
    return string(s).upper()


@word("lower", 1, "( S -- s )")
def _lower(s):
    return string(s).lower()


@word("trim", 1, "( s -- s )  strip surrounding whitespace")
def _trim(s):
    return string(s).strip()


@word("split", 2, "( s sep -- list )  sep \"\" splits into characters")
def _split(s, sep):
    s, sep = string(s), string(sep)
    if sep == "":
        return list(s)
    return s.split(sep)


@word("words", 1, "( s -- list )  split on runs of whitespace")
def _words(s):
    return string(s).split()


@word("lines", 1, "( s -- list )  split into lines")
def _lines(s):
    return string(s).splitlines()


@word("join", 2, "( list sep -- s )")
def _join(c, sep):
    return string(sep).join(show(x) for x in lst(c))


@word("replace", 3, "( s old new -- s )")
def _replace(s, old, new):
    return string(s).replace(string(old), string(new))


@word("starts-with?", 2, "( s prefix -- bool )")
def _starts(s, p):
    return string(s).startswith(string(p))


@word("ends-with?", 2, "( s suffix -- bool )")
def _ends(s, p):
    return string(s).endswith(string(p))


@word("chars", 1, "( s -- list )")
def _chars(s):
    return list(string(s))


@word("ord", 1, "( s -- n )  code point of the first character")
def _ord(s):
    if not string(s):
        raise ArgError("empty string")
    return ord(s[0])


@word("chr", 1, "( n -- s )")
def _chr(n):
    try:
        return chr(integer(n))
    except ValueError:
        raise ArgError(f"invalid code point {n}")


@word("pad-left", 3, "( s width fill -- s )")
def _pad_left(s, w, f):
    f = string(f)
    if len(f) != 1:
        raise ArgError("fill must be a single character")
    return show(s).rjust(integer(w), f)


@word("pad-right", 3, "( s width fill -- s )")
def _pad_right(s, w, f):
    f = string(f)
    if len(f) != 1:
        raise ArgError("fill must be a single character")
    return show(s).ljust(integer(w), f)


@word("fmt", 2, "( template list -- s )  replace each {} with the next element")
def _fmt(tmpl, args):
    tmpl, args = string(tmpl), lst(args)
    parts = tmpl.split("{}")
    if len(parts) - 1 != len(args):
        raise ArgError(f"template has {len(parts) - 1} placeholders but {len(args)} values were given")
    out = [parts[0]]
    for v, p in zip(args, parts[1:]):
        out.append(show(v))
        out.append(p)
    return "".join(out)


# ----------------------------------------------------------------------
# Types


@word("type", 1, "( x -- string )  int float string bool nil list dict quote function")
def _type(x):
    return type_name(x)


for _tn in ("int", "float", "string", "bool", "nil", "list", "dict", "quote", "function"):

    def _mk(tn):
        @word(f"{tn}?", 1, f"( x -- bool )  is x a {tn}?")
        def _is(x):
            return type_name(x) == tn

    _mk(_tn)


@word("number?", 1, "( x -- bool )")
def _is_number(x):
    return type(x) in (int, float)


@word("callable?", 1, "( x -- bool )")
def _is_callable(x):
    return is_callable(x)


# ----------------------------------------------------------------------
# Console I/O


@native("print", "( x -- )  print without newline")
def _print(interp):
    interp.stdout.write(show(interp.pop()))


@native("println", "( x -- )  print with newline")
def _println(interp):
    interp.stdout.write(show(interp.pop()) + "\n")


alias(".", "println")


@native("nl", "( -- )  print a newline")
def _nl(interp):
    interp.stdout.write("\n")


@native("eprintln", "( x -- )  print to stderr with newline")
def _eprintln(interp):
    interp.stdout.flush()
    interp.stderr.write(show(interp.pop()) + "\n")
    interp.stderr.flush()


@native(".s", "( -- )  show the whole stack")
def _dots(interp):
    st = interp.stack
    interp.stdout.write(f"<{len(st)}> " + " ".join(show(x, False) for x in st) + "\n")


@native("read-line", "( -- s|nil )  read a line from stdin (nil at end of input)")
def _read_line(interp):
    interp.stdout.flush()
    line = interp.stdin.readline()
    if line == "":
        interp.stack.append(None)
    else:
        interp.stack.append(line[:-1] if line.endswith("\n") else line)


@native("read-all", "( -- s )  read all of stdin")
def _read_all(interp):
    interp.stack.append(interp.stdin.read())


# ----------------------------------------------------------------------
# Files


def _os_error(e, path):
    return ArgError(f"{e.strerror or e} ({path})")


@word("read-file", 1, "( path -- s )")
def _read_file(path):
    try:
        with open(string(path), encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise _os_error(e, path)


@word("read-lines", 1, "( path -- list )")
def _read_lines(path):
    return _read_file(path).splitlines()


@word("write-file", 2, "( s path -- )  create or overwrite")
def _write_file(s, path):
    try:
        with open(string(path), "w", encoding="utf-8") as f:
            f.write(show(s))
    except OSError as e:
        raise _os_error(e, path)
    return NOTHING


@word("append-file", 2, "( s path -- )")
def _append_file(s, path):
    try:
        with open(string(path), "a", encoding="utf-8") as f:
            f.write(show(s))
    except OSError as e:
        raise _os_error(e, path)
    return NOTHING


@word("file-exists?", 1, "( path -- bool )")
def _file_exists(path):
    return os.path.exists(string(path))


@word("dir?", 1, "( path -- bool )")
def _is_dir(path):
    return os.path.isdir(string(path))


@word("delete-file", 1, "( path -- )")
def _delete_file(path):
    try:
        os.remove(string(path))
    except OSError as e:
        raise _os_error(e, path)
    return NOTHING


@word("list-dir", 1, "( path -- list )  sorted entry names")
def _list_dir(path):
    try:
        return sorted(os.listdir(string(path)))
    except OSError as e:
        raise _os_error(e, path)


@word("make-dir", 1, "( path -- )  create directory (and parents)")
def _make_dir(path):
    try:
        os.makedirs(string(path), exist_ok=True)
    except OSError as e:
        raise _os_error(e, path)
    return NOTHING


# ----------------------------------------------------------------------
# System


@native("args", "( -- list )  command-line arguments")
def _args(interp):
    interp.stack.append(list(interp.args))


@native("import", "( path -- )  load another Decaf file once (relative to the current file)")
def _import(interp):
    interp.import_file(string(interp.pop()))


@native("eval", "( s -- ... )  compile and run a string of Decaf code")
def _eval(interp):
    interp.execute(string(interp.pop()), "<eval>")


@word("getenv", 1, "( name -- s|nil )")
def _getenv(name):
    return os.environ.get(string(name))


@word("time", 0, "( -- seconds )  seconds since the epoch (float)")
def _time():
    return _clock.time()


@word("random", 0, "( -- x )  float in [0, 1)")
def _random():
    return _rnd.random()


@word("random-int", 2, "( lo hi -- n )  lo <= n <= hi")
def _random_int(lo, hi):
    return _rnd.randint(integer(lo), integer(hi))


@word("seed", 1, "( n -- )  seed the random generator")
def _seed(n):
    _rnd.seed(integer(n))
    return NOTHING


@native("all-words", "( -- list )  names of all builtin and user-defined words")
def _all_words(interp):
    interp.stack.append(sorted(set(BUILTINS) | set(interp.functions)))
