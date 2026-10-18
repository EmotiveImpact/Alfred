"""Adapted from: example-labs/tidy-memory
Path: src/tidy/store.py
Commit: a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1
Licence: MIT
Copyright: Copyright (c) 2025
  Example Labs

Synthetic adopted file with its credit in the module docstring. Inert text, never imported.
"""


def tidy(items):
    return [item for item in dict.fromkeys(items) if item]
