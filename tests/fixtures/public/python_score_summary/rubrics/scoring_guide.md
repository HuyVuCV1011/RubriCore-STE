# Scoring Guide: Score Summary

Total: 10 points

## Criteria

1. `average_score` behavior: 3 points
   - 2 points: correctly computes the average for non-empty score lists.
   - 1 point: returns `0` for an empty list.

2. `count_passing` behavior: 2 points
   - 1 point: counts scores greater than the threshold.
   - 1 point: includes scores equal to the threshold.

3. `score_report` behavior: 3 points
   - 1 point: returns a dictionary.
   - 1 point: includes correct `"average"` value.
   - 1 point: includes correct `"passing"` and `"total"` values.

4. Code quality and integration: 2 points
   - 1 point: function names and parameters match the prompt.
   - 1 point: code runs without syntax errors or unrelated output.

## Suggested Rule Checks

- Import the submitted Python file.
- Verify all three required functions exist.
- Run deterministic checks:
  - `average_score([80, 50, 70])`
  - `average_score([])`
  - `count_passing([60, 59, 100])`
  - `count_passing([40, 50, 60], passing_score=50)`
  - `score_report([80, 50, 70])`

## Feedback Notes

- Prefer specific feedback about missing edge cases, incorrect threshold handling, or incomplete report keys.
- Alternative valid implementations should receive full credit if behavior matches the prompt.
