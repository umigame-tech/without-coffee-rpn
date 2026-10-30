"""The Decaf virtual machine: a single data stack plus lexical environments."""

import os
import sys

from .builtins import BUILTINS
from .errors import (
    BreakSignal,
    ContinueSignal,
    ControlSignal,
    DecafError,
    ReturnSignal,
)
from .lexer import tokenize
from .parser import BIND, BUILTIN, FREF, LIST, PUSH, QUOTE, SET, SETG, WORD_, parse
from .values import BuiltinRef, Env, Function, Quotation, show, type_name


# Maximum nesting of function / quotation bodies being executed.
MAX_DEPTH = 200_000


class Interpreter:
    def __init__(self, args=None, stdin=None, stdout=None, stderr=None, max_depth=MAX_DEPTH):
        self.stack = []
        self.globals = Env()
        self.functions = {}
        self.args = list(args or [])
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.imported = set()
        # Directory of the file currently being loaded (for relative imports).
        self.dir_stack = [os.getcwd()]
        self.depth = 0
        self.max_depth = max_depth

    # ------------------------------------------------------------------
    # Loading code

    def compile(self, src, filename="<input>"):
        return parse(tokenize(src, filename), BUILTINS)

    def define(self, program):
        for d in program.defs:
            self.functions[d.name] = Function(d.name, d.code, d.pos)

    def execute(self, src, filename="<input>"):
        """Compile and run a piece of source code in the global environment."""
        program = self.compile(src, filename)
        self.define(program)
        self.run(program.code, self.globals)

    def run_file(self, path):
        path = os.path.abspath(path)
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            raise DecafError(f"cannot open '{path}': {e.strerror}")
        self.imported.add(path)
        self.dir_stack.append(os.path.dirname(path))
        try:
            rel = os.path.relpath(path)
            self.execute(src, path if rel.startswith("..") else rel)
        finally:
            self.dir_stack.pop()

    def import_file(self, path):
        full = os.path.abspath(os.path.join(self.dir_stack[-1], path))
        if not os.path.exists(full) and not full.endswith(".dcf"):
            full += ".dcf"
        if full in self.imported:
            return
        self.run_file(full)

    # ------------------------------------------------------------------
    # Stack helpers

    def push(self, v):
        self.stack.append(v)

    def pop(self):
        try:
            return self.stack.pop()
        except IndexError:
            raise DecafError("stack underflow")

    # ------------------------------------------------------------------
    # Execution

    def run(self, code, env):
        if self.depth >= self.max_depth:
            raise DecafError(f"maximum recursion depth exceeded ({self.max_depth})")
        self.depth += 1
        try:
            self._run(code, env)
        finally:
            self.depth -= 1

    def _run(self, code, env):
        stack = self.stack
        for op, arg, pos in code:
            try:
                if op == BUILTIN:
                    arg(self)
                elif op == PUSH:
                    stack.append(arg)
                elif op == WORD_:
                    e = env
                    while e is not None:
                        vars_ = e.vars
                        if arg in vars_:
                            stack.append(vars_[arg])
                            break
                        e = e.parent
                    else:
                        fn = self.functions.get(arg)
                        if fn is None:
                            raise DecafError(f"unknown word '{arg}'")
                        self.call_function(fn)
                elif op == QUOTE:
                    stack.append(Quotation(arg, env))
                elif op == SET:
                    if not stack:
                        raise DecafError(f"stack underflow (assigning '{arg}')")
                    env.vars[arg] = stack.pop()
                elif op == SETG:
                    if not stack:
                        raise DecafError(f"stack underflow (assigning '{arg}')")
                    self.globals.vars[arg] = stack.pop()
                elif op == BIND:
                    n = len(arg)
                    if len(stack) < n:
                        raise DecafError(
                            f"stack underflow: binding | {' '.join(arg)} | needs {n} values, "
                            f"stack has {len(stack)}"
                        )
                    vals = stack[len(stack) - n :]
                    del stack[len(stack) - n :]
                    vars_ = env.vars
                    for name, v in zip(arg, vals):
                        vars_[name] = v
                elif op == LIST:
                    mark = len(stack)
                    self.run(arg, env)
                    if len(stack) < mark:
                        raise DecafError("list literal consumed values from outside its braces")
                    items = stack[mark:]
                    del stack[mark:]
                    stack.append(items)
                elif op == FREF:
                    stack.append(self.lookup_function(arg))
            except DecafError as e:
                e.add_trace(pos)
                raise
            except ControlSignal:
                raise
            except RecursionError:
                err = DecafError("maximum recursion depth exceeded")
                err.add_trace(pos)
                raise err
            except ZeroDivisionError:
                err = DecafError("division by zero")
                err.add_trace(pos)
                raise err
            except (OverflowError, ValueError, TypeError) as ex:
                err = DecafError(str(ex))
                err.add_trace(pos)
                raise err

    def lookup_function(self, name):
        fn = self.functions.get(name)
        if fn is not None:
            return fn
        b = BUILTINS.get(name)
        if b is not None:
            return BuiltinRef(name, b)
        raise DecafError(f"unknown function '&{name}'")

    def call_function(self, fn):
        try:
            self.run(fn.code, Env(self.globals))
        except ReturnSignal:
            pass
        except (BreakSignal, ContinueSignal):
            raise DecafError(f"'break' or 'continue' used outside of a loop in '{fn.name}'")
        except DecafError as e:
            e.name_frames(fn.name)
            raise

    def call(self, v):
        """Invoke a callable value (quotation, function or builtin reference)."""
        t = type(v)
        if t is Quotation:
            self.run(v.code, v.env)
        elif t is Function:
            self.call_function(v)
        elif t is BuiltinRef:
            v.fn(self)
        else:
            raise DecafError(f"cannot call a value of type {type_name(v)} ({show(v, False)})")

    def call_with(self, fn, *args):
        """Push args, call fn and pop a single result."""
        self.stack.extend(args)
        depth = len(self.stack) - len(args)
        self.call(fn)
        if len(self.stack) != depth + 1:
            got = len(self.stack) - depth
            raise DecafError(f"callback was expected to leave exactly 1 value, left {got}")
        return self.stack.pop()
