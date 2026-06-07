#!/usr/bin/env python3
from __future__ import annotations

import sys

from codex_with_cc_runtime.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["ccclean", *sys.argv[1:]]))
