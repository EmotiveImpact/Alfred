# Adapted from: example-labs/tidy-memory
# Path: src/tidy/store.py
# Commit: a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1
# Licence: MIT
# Copyright: Copyright (c) 2025 Example Labs
# Changes: Rewritten to ALFRED's conventions; only the ranking helper is kept.
"""Synthetic adopted file for tests/test_check_adoptions.py. Inert text, never imported."""


def rank(items, weights=None):
    weights = weights or {}
    return sorted(items, key=lambda item: -weights.get(item, 0))
