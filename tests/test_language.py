import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from decaf import DecafError, Interpreter  # noqa: E402
from decaf.errors import ParseError  # noqa: E402

sys.setrecursionlimit(4_000_000)
threading.stack_size(512 * 1024 * 1024)


def run(src, stdin="", args=None):
    """Run src on a big-stack thread; return (stdout, stack)."""
    out = io.StringIO()
    interp = Interpreter(args=args, stdin=io.StringIO(stdin), stdout=out, stderr=io.StringIO())
    box = {}

    def target():
        try:
            interp.execute(src, "<test>")
        except BaseException as e:
            box["error"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return out.getvalue(), interp.stack


def stack(src, **kw):
    return run(src, **kw)[1]


def output(src, **kw):
    return run(src, **kw)[0]


class ArithmeticTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(stack("1 2 +"), [3])
        self.assertEqual(stack("10 4 -"), [6])
        self.assertEqual(stack("3 4 * 5 +"), [17])
        self.assertEqual(stack("3 4 5 * +"), [23])

    def test_division(self):
        self.assertEqual(stack("6 2 /"), [3])
        self.assertEqual(stack("7 2 /"), [3.5])
        self.assertEqual(stack("7 2 div"), [3])
        self.assertEqual(stack("-7 2 mod"), [1])
        with self.assertRaises(DecafError):
            stack("1 0 /")

    def test_numbers(self):
        self.assertEqual(stack("0x1F 0b101 -3 2.5 1e3"), [31, 5, -3, 2.5, 1000.0])
        self.assertEqual(stack("2 100 **"), [2**100])
        self.assertEqual(stack("16 sqrt 2 sqrt"), [4, 2**0.5])

    def test_comparison_and_logic(self):
        self.assertEqual(stack("1 2 < 2 1 < 2 2 <= 1 1 ="), [True, False, True, True])
        self.assertEqual(stack('"a" "b" <'), [True])
        self.assertEqual(stack("true false and true false or false not"), [False, True, True])
        self.assertEqual(stack("nil 5 or 0 7 and"), [5, 0])
        self.assertEqual(stack("1 true ="), [False])
        self.assertEqual(stack("1 1.0 ="), [True])
        self.assertEqual(stack("{ 1 { 2 } } { 1 { 2 } } ="), [True])


class StackTest(unittest.TestCase):
    def test_shuffles(self):
        self.assertEqual(stack("1 dup"), [1, 1])
        self.assertEqual(stack("1 2 swap"), [2, 1])
        self.assertEqual(stack("1 2 over"), [1, 2, 1])
        self.assertEqual(stack("1 2 3 rot"), [2, 3, 1])
        self.assertEqual(stack("1 2 3 -rot"), [3, 1, 2])
        self.assertEqual(stack("1 2 nip"), [2])
        self.assertEqual(stack("1 2 tuck"), [2, 1, 2])
        self.assertEqual(stack("1 2 3 2 pick"), [1, 2, 3, 1])
        self.assertEqual(stack("1 2 3 depth"), [1, 2, 3, 3])

    def test_underflow(self):
        with self.assertRaises(DecafError) as cm:
            stack("1 +")
        self.assertIn("stack underflow", cm.exception.msg)


class VariableTest(unittest.TestCase):
    def test_assign(self):
        self.assertEqual(stack("5 -> x x x *"), [25])

    def test_bind(self):
        self.assertEqual(stack("1 2 3 | a b c | c b a"), [3, 2, 1])

    def test_function_locals_are_isolated(self):
        src = """
        1 -> x
        : f 99 -> x x ;
        f x
        """
        self.assertEqual(stack(src), [99, 1])

    def test_global_assign(self):
        self.assertEqual(stack(": setg 42 => g ; setg g"), [42])

    def test_function_reads_globals(self):
        self.assertEqual(stack("10 -> base : add-base base + ; 5 add-base"), [15])

    def test_closure_captures_locals(self):
        src = """
        : adder | n | [ n + ] ;
        3 adder -> add3
        10 add3 call
        """
        self.assertEqual(stack(src), [13])

    def test_quotation_mutates_enclosing_local(self):
        src = """
        : count-to | n | 0 -> c [ c n < ] [ c 1 + -> c ] while c ;
        7 count-to
        """
        self.assertEqual(stack(src), [7])

    def test_builtin_name_rejected(self):
        with self.assertRaises(ParseError):
            stack("1 -> dup")
        with self.assertRaises(ParseError):
            stack(": + ;")


class FunctionTest(unittest.TestCase):
    def test_define_and_call(self):
        self.assertEqual(stack(": sq dup * ; 9 sq"), [81])

    def test_hoisting(self):
        self.assertEqual(stack("4 double : double 2 * ;"), [8])

    def test_recursion(self):
        src = ": fact | n | n 1 <= [ 1 ] [ n 1 - fact n * ] if ; 20 fact"
        self.assertEqual(stack(src), [2432902008176640000])

    def test_mutual_recursion(self):
        src = """
        : even? | n | n 0 = [ true ] [ n 1 - odd? ] if ;
        : odd?  | n | n 0 = [ false ] [ n 1 - even? ] if ;
        10 even? 7 even?
        """
        self.assertEqual(stack(src), [True, False])

    def test_deep_recursion(self):
        src = ": down | n | n 0 = [ 0 ] [ n 1 - down 1 + ] if ; 50000 down"
        self.assertEqual(stack(src), [50000])

    def test_recursion_limit_is_an_error(self):
        interp_src = ": inf inf ; inf"
        with self.assertRaises(DecafError) as cm:
            stack(interp_src)
        self.assertIn("recursion", cm.exception.msg)

    def test_return(self):
        self.assertEqual(stack(": f 1 return 2 ; f"), [1])

    def test_return_from_inside_loop(self):
        src = ": first-even [ | x | x 2 mod 0 = [ x return ] when ] each nil ; { 1 3 6 8 } first-even"
        self.assertEqual(stack(src), [6])

    def test_function_reference(self):
        self.assertEqual(stack(": sq dup * ; { 1 2 3 } &sq map"), [[1, 4, 9]])
        self.assertEqual(stack("3 4 &+ call"), [7])

    def test_duplicate_definition(self):
        with self.assertRaises(ParseError):
            stack(": f ; : f ;")

    def test_unknown_word(self):
        with self.assertRaises(DecafError) as cm:
            stack("frobnicate")
        self.assertIn("unknown word", cm.exception.msg)
        self.assertEqual(cm.exception.pos.line, 1)


class ControlFlowTest(unittest.TestCase):
    def test_if(self):
        self.assertEqual(stack('1 2 < [ "yes" ] [ "no" ] if'), ["yes"])
        self.assertEqual(stack('1 2 > [ "yes" ] [ "no" ] if'), ["no"])

    def test_when_unless(self):
        self.assertEqual(stack("true [ 1 ] when false [ 2 ] when false [ 3 ] unless"), [1, 3])

    def test_cond(self):
        src = """
        : sign | n | { [ n 0 < ] [ -1 ] [ n 0 = ] [ 0 ] [ true ] [ 1 ] } cond ;
        -5 sign 0 sign 9 sign
        """
        self.assertEqual(stack(src), [-1, 0, 1])

    def test_while(self):
        self.assertEqual(stack("1 -> n [ n 100 < ] [ n 2 * -> n ] while n"), [128])

    def test_times_and_for(self):
        self.assertEqual(stack("0 5 [ 1 + ] times"), [5])
        self.assertEqual(stack("0 1 5 [ + ] for"), [10])
        self.assertEqual(stack("0 10 0 -3 [ + ] for-step"), [10 + 7 + 4 + 1])

    def test_break_continue(self):
        src = "0 { 1 2 3 4 5 6 } [ | x | x 2 = [ continue ] when x 5 = [ break ] when x + ] each"
        self.assertEqual(stack(src), [1 + 3 + 4])
        self.assertEqual(stack("0 -> i [ i 1 + -> i i 10 = [ break ] when ] loop i"), [10])

    def test_break_outside_loop(self):
        with self.assertRaises(DecafError):
            stack(": f break ; f")

    def test_each_dict(self):
        self.assertEqual(stack('{ } dict "a" 1 put "b" 2 put [ | k v | k push ] each'), [["a", "b"]])

    def test_try_throw(self):
        self.assertEqual(stack('[ "boom" throw ] [ "caught " swap + ] try'), ["caught boom"])
        self.assertEqual(stack("[ 1 2 3 { } throw ] [ type ] try"), ["list"])
        self.assertEqual(stack('[ 1 0 / ] [ "division by zero" contains? ] try'), [True])
        # stack is restored to its depth before the body ran
        self.assertEqual(stack('9 [ 1 2 "x" throw ] [ drop ] try'), [9])

    def test_assert(self):
        with self.assertRaises(DecafError):
            stack('1 2 = "math is broken" assert')


class StringTest(unittest.TestCase):
    def test_literals_and_escapes(self):
        self.assertEqual(stack(r'"a\tb\n\"c\"\\ \u{3042}"'), ['a\tb\n"c"\\ あ'])

    def test_operations(self):
        self.assertEqual(stack('"foo" "bar" +'), ["foobar"])
        self.assertEqual(stack('"hello" len'), [5])
        self.assertEqual(stack('"Hello" upper "Hello" lower'), ["HELLO", "hello"])
        self.assertEqual(stack('"a,b,c" "," split'), [["a", "b", "c"]])
        self.assertEqual(stack('{ 1 "x" 2.5 } "-" join'), ["1-x-2.5"])
        self.assertEqual(stack('"hello world" "o" "0" replace'), ["hell0 w0rld"])
        self.assertEqual(stack('"hello" 1 3 slice'), ["el"])
        self.assertEqual(stack('"  pad  " trim'), ["pad"])
        self.assertEqual(stack('"hello" "ll" index-of "hello" "z" index-of'), [2, -1])
        self.assertEqual(stack('"abc" reverse "ab" 3 *'), ["cba", "ababab"])
        self.assertEqual(stack('"A" ord 97 chr'), [65, "a"])
        self.assertEqual(stack('"x={} y={}" { 1 "two" } fmt'), ["x=1 y=two"])
        self.assertEqual(stack('"42" num "3.5" num "nope" num'), [42, 3.5, None])
        self.assertEqual(stack('3.9 int "17" int 2 float'), [3, 17, 2.0])
        self.assertEqual(stack("12 str { 1 \"a\" } str"), ["12", '{ 1 "a" }'])
        self.assertEqual(stack('"abc" [ upper ] map'), ["ABC"])

    def test_string_plus_number_is_error(self):
        with self.assertRaises(DecafError):
            stack('"n=" 1 +')


class CollectionTest(unittest.TestCase):
    def test_list_literal_evaluates(self):
        self.assertEqual(stack("{ 1 2 + 4 { 5 } }"), [[3, 4, [5]]])

    def test_list_ops(self):
        self.assertEqual(stack("{ 1 2 } 3 push"), [[1, 2, 3]])
        self.assertEqual(stack("{ 1 2 3 } pop"), [[1, 2], 3])
        self.assertEqual(stack("{ 5 6 7 } 1 get { 5 6 7 } -1 get"), [6, 7])
        self.assertEqual(stack("{ 5 6 7 } 0 9 put"), [[9, 6, 7]])
        self.assertEqual(stack("{ 3 1 2 } sort { 1 2 } { 3 } +"), [[1, 2, 3], [1, 2, 3]])
        self.assertEqual(stack("1 5 range sum"), [10])
        self.assertEqual(stack("{ 1 2 3 } first { 1 2 3 } last { 1 2 3 } rest"), [1, 3, [2, 3]])
        self.assertEqual(stack("{ 1 2 3 } spread"), [1, 2, 3])
        self.assertEqual(stack("1 2 3 3 collect"), [[1, 2, 3]])
        self.assertEqual(stack("{ 1 2 3 } 2 contains?"), [True])

    def test_index_error(self):
        with self.assertRaises(DecafError):
            stack("{ 1 } 5 get")

    def test_higher_order(self):
        self.assertEqual(stack("{ 1 2 3 4 } [ 2 mod 0 = ] filter"), [[2, 4]])
        self.assertEqual(stack("{ 1 2 3 4 } 0 [ + ] reduce"), [10])
        self.assertEqual(stack("{ 1 2 3 4 } [ 2 > ] find"), [3])
        self.assertEqual(stack('{ "ccc" "a" "bb" } [ len ] sort-by'), [["a", "bb", "ccc"]])
        self.assertEqual(stack("{ 1 2 } [ 0 > ] all? { 1 2 } [ 1 > ] any?"), [True, True])

    def test_dict(self):
        src = 'dict "a" 1 put "b" 2 put -> d d "a" get d "z" get d "b" has? d keys d len'
        self.assertEqual(stack(src), [1, None, True, ["a", "b"], 2])


class IOTest(unittest.TestCase):
    def test_print(self):
        self.assertEqual(output('"hi" println 1 print 2 . { "s" } .'), 'hi\n12\n{ "s" }\n')

    def test_read_line(self):
        self.assertEqual(stack("read-line read-line read-line", stdin="a\nb\n"), ["a", "b", None])

    def test_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt").replace("\\", "/")
            src = f'''
            "one\\n" "{p}" write-file
            "two\\n" "{p}" append-file
            "{p}" read-file
            "{p}" read-lines
            "{p}" file-exists?
            "{p}" delete-file
            "{p}" file-exists?
            '''
            self.assertEqual(stack(src), ["one\ntwo\n", ["one", "two"], True, False])

    def test_missing_file_is_catchable(self):
        self.assertEqual(stack('[ "/no/such/file" read-file ] [ drop "caught" ] try'), ["caught"])

    def test_args(self):
        self.assertEqual(stack("args", args=["x", "y"]), [["x", "y"]])

    def test_import(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lib.dcf"), "w") as f:
                f.write(": triple 3 * ;\n")
            with open(os.path.join(d, "main.dcf"), "w") as f:
                f.write('"lib.dcf" import "lib" import 5 triple\n')
            interp = Interpreter(stdout=io.StringIO())
            interp.run_file(os.path.join(d, "main.dcf"))
            self.assertEqual(interp.stack, [15])

    def test_eval(self):
        self.assertEqual(stack('"1 2 +" eval'), [3])

    def test_system_words(self):
        self.assertEqual(stack("time float? random float? 1 6 random-int int? 1 type"), [True, True, True, "int"])


class SyntaxTest(unittest.TestCase):
    def test_comments(self):
        self.assertEqual(stack("1 # comment\n( a -- b (nested) ) 2"), [1, 2])

    def test_unclosed(self):
        for src in ["[ 1 2", "{ 1", ": f 1", '"abc', "| a b"]:
            with self.assertRaises(ParseError) as cm:
                stack(src)
            self.assertTrue(cm.exception.incomplete, src)

    def test_unexpected_closer(self):
        with self.assertRaises(ParseError):
            stack("1 ]")

    def test_nested_definition_rejected(self):
        with self.assertRaises(ParseError):
            stack("[ : f ; ]")

    def test_error_position(self):
        with self.assertRaises(DecafError) as cm:
            stack("1 2 +\n  3 \"x\" +")
        self.assertEqual((cm.exception.pos.line, cm.exception.pos.col), (2, 9))


class CLITest(unittest.TestCase):
    def cli(self, *argv, stdin=""):
        env = dict(os.environ, PYTHONPATH=ROOT)
        return subprocess.run(
            [sys.executable, "-m", "decaf", *argv],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )

    def test_eval(self):
        r = self.cli("-e", "1 2 + .")
        self.assertEqual((r.returncode, r.stdout), (0, "3\n"))

    def test_eval_with_args(self):
        r = self.cli("-e", "args .", "a", "b")
        self.assertEqual(r.stdout, '{ "a" "b" }\n')

    def test_run_file_with_args(self):
        r = self.cli("examples/primes.dcf", "30")
        self.assertEqual(r.returncode, 0)
        self.assertIn("2 3 5 7 11 13 17 19 23 29", r.stdout)

    def test_stdin_program(self):
        r = self.cli(stdin='"from stdin" .')
        self.assertEqual(r.stdout, "from stdin\n")

    def test_exit_code(self):
        self.assertEqual(self.cli("-e", "7 exit").returncode, 7)

    def test_error_exit(self):
        r = self.cli("-e", "1 0 /")
        self.assertEqual(r.returncode, 1)
        self.assertIn("division by zero", r.stderr)

    def test_check(self):
        self.assertEqual(self.cli("--check", "examples/hello.dcf").returncode, 0)
        with tempfile.NamedTemporaryFile("w", suffix=".dcf", delete=False) as f:
            f.write("[ 1 2")
        try:
            r = self.cli("--check", f.name)
            self.assertEqual(r.returncode, 1)
            self.assertIn("syntax error", r.stderr)
        finally:
            os.unlink(f.name)

    def test_repl(self):
        r = self.cli("-e", "1 2", "-i", stdin=": sq dup *\n ;\n+ sq .\nnope\n")
        self.assertIn("9", r.stdout)
        self.assertIn("unknown word 'nope'", r.stderr)
        self.assertEqual(r.returncode, 0)

    def test_words(self):
        r = self.cli("--words")
        self.assertIn("dup", r.stdout)


if __name__ == "__main__":
    unittest.main()
