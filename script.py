import sys
import unittest
from collections.abc import Callable


def entry(name: str, main: Callable[..., object], *args: object, **kwargs: object) -> None:
    if name == "__main__":
        code = main(*args, **kwargs)
        sys.exit(code if isinstance(code, int) else None)


def skip_unless(present: object, reason: str) -> None:
    if not present:
        raise unittest.SkipTest(reason)


def needed[T](value: T | None, reason: str) -> T:
    if value is None:
        raise unittest.SkipTest(reason)
    return value
