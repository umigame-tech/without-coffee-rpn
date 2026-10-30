"""Command-line interface: run Decaf programs, one-liners, or an interactive REPL."""

import argparse
import ctypes
import sys
import threading

from . import __version__
from .builtins import DOCS
from .errors import DecafError, ExitSignal, ParseError, ReturnSignal, ControlSignal
from .interpreter import Interpreter
from .values import show

# Deep recursion in Decaf maps onto Python recursion, so run on a thread
# with a large native stack and a generous recursion limit.
STACK_SIZE = 1024 * 1024 * 1024
RECURSION_LIMIT = 4_000_000


def run_big(fn):
    """Run fn() on a thread with a large stack; Ctrl-C interrupts it."""
    box = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as e:  # re-raised in the calling thread
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    while t.is_alive():
        try:
            t.join()
        except KeyboardInterrupt:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(t.ident), ctypes.py_object(KeyboardInterrupt)
            )
    if "error" in box:
        raise box["error"]
    return box.get("result")


def run_guarded(interp, action):
    """Run `action()` and turn Decaf errors into an exit status."""
    try:
        action()
        return 0
    except ExitSignal as e:
        return e.code
    except ReturnSignal:
        return 0
    except ControlSignal:
        interp.stdout.flush()
        print("error: 'break' or 'continue' used outside of a loop", file=sys.stderr)
        return 1
    except DecafError as e:
        interp.stdout.flush()
        print(e.format(), file=sys.stderr)
        return 1
    finally:
        interp.stdout.flush()


def repl(interp):
    try:
        import readline  # noqa: F401  (line editing / history when available)
    except ImportError:
        pass

    print(f"Decaf {__version__} REPL — type 'help' for help, Ctrl-D to quit.")
    buf = ""
    while True:
        try:
            line = input("... " if buf else "> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\n(interrupted)")
            buf = ""
            continue

        if not buf:
            cmd = line.strip()
            if cmd in ("quit", "exit"):
                return 0
            if cmd == "help":
                print_repl_help()
                continue
            if cmd.startswith("help "):
                name = cmd[5:].strip()
                if name in DOCS:
                    print(f"{name}  {DOCS[name]}")
                else:
                    print(f"no builtin named '{name}'")
                continue

        src = buf + line + "\n"
        try:
            program = interp.compile(src, "<repl>")
        except ParseError as e:
            if e.incomplete:
                buf = src
                continue
            print(e.format(), file=sys.stderr)
            buf = ""
            continue
        buf = ""

        snapshot = list(interp.stack)

        def evaluate():
            interp.define(program)
            interp.run(program.code, interp.globals)

        try:
            run_big(evaluate)
        except ExitSignal as e:
            return e.code
        except ReturnSignal:
            pass
        except ControlSignal:
            print("error: 'break' or 'continue' used outside of a loop", file=sys.stderr)
            interp.stack[:] = snapshot
        except DecafError as e:
            interp.stdout.flush()
            print(e.format(), file=sys.stderr)
            interp.stack[:] = snapshot
            print("(stack restored)", file=sys.stderr)
        except KeyboardInterrupt:
            print("\n(interrupted)")
            interp.stack[:] = snapshot
        interp.stdout.flush()
        if interp.stack:
            print("  <" + str(len(interp.stack)) + "> " + " ".join(show(v, False) for v in interp.stack))


def print_repl_help():
    print(
        "Enter Decaf code; the stack is shown after each line.\n"
        "  help <word>   show the stack effect of a builtin\n"
        "  quit          leave the REPL (or press Ctrl-D)\n"
        "Example:  : sq dup * ;  7 sq ."
    )


def list_words():
    width = max(len(n) for n in DOCS)
    for name in sorted(DOCS):
        print(f"{name.ljust(width)}  {DOCS[name]}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="decaf",
        description="Decaf — a stack-based programming language in Reverse Polish Notation.",
        epilog="With no FILE and no -e, starts a REPL (or reads a program from stdin when it is not a terminal).",
    )
    p.add_argument("file", nargs="?", help="Decaf source file to run (use '-' for stdin)")
    p.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the program (see 'args')")
    p.add_argument("-e", "--eval", metavar="CODE", help="run CODE instead of a file")
    p.add_argument("-c", "--check", action="store_true", help="only check FILE for syntax errors")
    p.add_argument("-i", "--interactive", action="store_true", help="start a REPL after running FILE / CODE")
    p.add_argument("--words", action="store_true", help="list all builtin words and exit")
    p.add_argument("--version", action="version", version=f"Decaf {__version__}")
    return p


def real_main(argv):
    opts = build_parser().parse_args(argv)

    if opts.words:
        list_words()
        return 0

    prog_args = list(opts.args)
    if opts.eval is not None and opts.file is not None:
        # With -e, every positional is a program argument.
        prog_args = [opts.file] + prog_args

    interp = Interpreter(args=prog_args)

    if opts.check:
        if not opts.file:
            print("decaf: --check needs a FILE", file=sys.stderr)
            return 2
        try:
            with open(opts.file, encoding="utf-8") as f:
                interp.compile(f.read(), opts.file)
        except OSError as e:
            print(f"decaf: cannot open '{opts.file}': {e.strerror}", file=sys.stderr)
            return 2
        except ParseError as e:
            print(e.format(), file=sys.stderr)
            return 1
        print(f"{opts.file}: ok")
        return 0

    if opts.eval is not None:
        action = lambda: interp.execute(opts.eval, "<eval>")  # noqa: E731
    elif opts.file == "-" or (opts.file is None and not sys.stdin.isatty()):
        src = sys.stdin.read()
        action = lambda: interp.execute(src, "<stdin>")  # noqa: E731
    elif opts.file is not None:
        action = lambda: interp.run_file(opts.file)  # noqa: E731
    else:
        return repl(interp)

    try:
        status = run_big(lambda: run_guarded(interp, action))
    except KeyboardInterrupt:
        sys.stdout.flush()
        print("\ninterrupted", file=sys.stderr)
        return 130

    if opts.interactive:
        return repl(interp)
    return status


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    sys.setrecursionlimit(RECURSION_LIMIT)
    threading.stack_size(STACK_SIZE)
    try:
        status = real_main(argv)
    except BrokenPipeError:
        status = 0
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        pass
    sys.exit(status)
