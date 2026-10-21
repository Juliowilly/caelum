#!/usr/bin/env python3
"""Compatibility launcher: `python3 desktop_tracker.py` keeps working from a source checkout.

The code now lives in the `caelum` package; prefer `python3 -m caelum` or the installed `caelum` command.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from caelum.gtk_ui.app import main  # noqa: E402

if __name__ == '__main__':
    main()
