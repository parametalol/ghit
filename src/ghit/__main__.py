#!/usr/bin/env python3

import sys
from .ghit import ghit


def main() -> int:
    return ghit(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
