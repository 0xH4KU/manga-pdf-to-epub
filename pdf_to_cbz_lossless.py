#!/usr/bin/env python3
"""Compatibility wrapper for the CBZ converter CLI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from manga_pdf_to_epub.pdf_to_cbz_lossless import main


if __name__ == "__main__":
    raise SystemExit(main())
