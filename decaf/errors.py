"""Error types and source positions."""


class SourcePos:
    __slots__ = ("file", "line", "col")

    def __init__(self, file, line, col):
        self.file = file
        self.line = line
        self.col = col

    def __str__(self):
        return f"{self.file}:{self.line}:{self.col}"

    def __eq__(self, other):
        return (
            isinstance(other, SourcePos)
            and self.file == other.file
            and self.line == other.line
            and self.col == other.col
        )

    def __hash__(self):
        return hash((self.file, self.line, self.col))


class DecafError(Exception):
    """A runtime or compile-time error raised by a Decaf program."""

    def __init__(self, msg, pos=None, value=None):
        super().__init__(msg)
        self.msg = msg
        self.pos = pos
        # The value passed to `throw` (or the message string for builtin errors).
        self.value = msg if value is None else value
        # List of [SourcePos, function-name-or-None], innermost first.
        self.trace = []
        self._named = 0  # entries before this index already carry a function name

    def add_trace(self, pos):
        if self.pos is None:
            self.pos = pos
        if not self.trace or self.trace[-1][0] != pos:
            self.trace.append([pos, None])

    def name_frames(self, fn_name):
        trace = self.trace
        for i in range(self._named, len(trace)):
            trace[i][1] = fn_name
        self._named = len(trace)

    def format(self, limit=12):
        where = f"{self.pos}: " if self.pos is not None else ""
        lines = [f"{where}error: {self.msg}"]
        frames = [f"  at {pos} (in {name or 'top level'})" for pos, name in self.trace]
        frames = _fold_repeats(frames)
        if len(frames) > limit:
            hidden = len(frames) - limit
            frames = frames[: limit - 2] + [f"  ... {hidden} more frames ..."] + frames[-2:]
        return "\n".join(lines + frames)


def _fold_repeats(lines, max_period=4):
    """Collapse runs of a repeating block of lines (deep recursion)."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        folded = False
        for p in range(1, max_period + 1):
            if i < p:
                continue
            j = i
            while j < n and lines[j] == lines[j - p]:
                j += 1
            reps = (j - i) // p
            if reps >= 2:
                out.append(f"  ... (the {p} line{'s' if p > 1 else ''} above repeated {reps} more times)")
                i += reps * p
                folded = True
                break
        if not folded:
            out.append(lines[i])
            i += 1
    return out


class ParseError(DecafError):
    """Syntax error. `incomplete` is True when more input could fix it (REPL)."""

    def __init__(self, msg, pos=None, incomplete=False):
        super().__init__(msg, pos)
        self.incomplete = incomplete

    def format(self, limit=12):
        where = f"{self.pos}: " if self.pos is not None else ""
        return f"{where}syntax error: {self.msg}"


class ControlSignal(Exception):
    """Base class for non-error control flow (break / continue / return / exit)."""


class BreakSignal(ControlSignal):
    pass


class ContinueSignal(ControlSignal):
    pass


class ReturnSignal(ControlSignal):
    pass


class ExitSignal(ControlSignal):
    def __init__(self, code):
        super().__init__(code)
        self.code = code
