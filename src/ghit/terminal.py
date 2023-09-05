import sys


def stdout(*args, **kwargs):
    print(*args, **kwargs)  # noqa: T201


def stderr(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)  # noqa: T201
