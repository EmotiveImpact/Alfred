// Adapted from: sample-works/graph-kit
// Path: graph/rank.ts
// Commit: b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2
// Licence: Apache-2.0
// Notice: Graph Kit
//   Copyright 2024 Sample Works Ltd.
// Changes: Ported to the console's types and renamed the export.
// Synthetic adopted file for tests/test_check_adoptions.py. Inert text, never run.

export function rankScores(scores: number[]): number[] {
  return [...scores].sort((a, b) => b - a);
}
