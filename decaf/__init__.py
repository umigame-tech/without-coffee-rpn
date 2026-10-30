"""Decaf: a general-purpose, stack-based programming language in Reverse Polish Notation."""

__version__ = "0.1.0"

from .errors import DecafError  # noqa: E402,F401
from .interpreter import Interpreter  # noqa: E402,F401

__all__ = ["DecafError", "Interpreter", "__version__"]
