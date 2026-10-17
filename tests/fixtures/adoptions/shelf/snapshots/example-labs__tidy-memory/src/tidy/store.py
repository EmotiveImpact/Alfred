"""Synthetic upstream file for tests/test_check_adoptions.py. Inert text, never imported."""


def rank(items, weights=None):
    """Order items by weight, highest first, keeping the original order for ties."""
    weights = weights or {}
    return sorted(items, key=lambda item: -weights.get(item, 0))


def tidy(items):
    """Drop blanks and duplicates while keeping the first occurrence."""
    seen, kept = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            kept.append(item)
    return kept
