"""Golden tests: run every program in examples/ and compare its output."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
EXPECTED = os.path.join(ROOT, "tests", "expected")

# example name -> (args, stdin)
INPUTS = {
    "calc": ([], "3 4 + 2 *\n1 2 3\n10 0 /\n2 10 ^ 3 -\n5 x\n1.5 2 * 7 max\n"),
    "primes": (["100"], ""),
    "wordcount": (["input.txt", "report.txt"], ""),
}

WORDCOUNT_INPUT = "The quick brown fox. The lazy dog! the end, fox.\n"


def run_example(name):
    args, stdin = INPUTS.get(name, ([], ""))
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "input.txt"), "w") as f:
            f.write(WORDCOUNT_INPUT)
        # run from a scratch directory so file-writing examples leave no trace
        shutil.copytree(EXAMPLES, os.path.join(tmp, "examples"))
        r = subprocess.run(
            [sys.executable, "-m", "decaf", os.path.join("examples", f"{name}.dcf"), *args],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=tmp,
            env=dict(os.environ, PYTHONPATH=ROOT),
        )
        out = r.stdout
        if name == "wordcount":
            with open(os.path.join(tmp, "report.txt")) as f:
                out += "--- report.txt ---\n" + f.read()
        return r.returncode, out, r.stderr


class ExamplesTest(unittest.TestCase):
    pass


def make_test(name):
    def test(self):
        code, out, err = run_example(name)
        self.assertEqual(code, 0, err)
        with open(os.path.join(EXPECTED, f"{name}.out"), encoding="utf-8") as f:
            self.assertEqual(out, f.read())

    return test


for _file in sorted(os.listdir(EXAMPLES)):
    if _file.endswith(".dcf"):
        _name = _file[:-4]
        setattr(ExamplesTest, f"test_{_name.replace('-', '_')}", make_test(_name))


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        for _file in sorted(os.listdir(EXAMPLES)):
            if _file.endswith(".dcf"):
                _code, _out, _err = run_example(_file[:-4])
                assert _code == 0, _err
                with open(os.path.join(EXPECTED, _file[:-4] + ".out"), "w", encoding="utf-8") as f:
                    f.write(_out)
                print("updated", _file)
    else:
        unittest.main()
