# Exercise: Score Summary

Write a Python file that defines the following functions.

## Function 1: `average_score(scores)`

Return the average of a list of numeric quiz scores.

- If `scores` is empty, return `0`.
- The result may be an integer or a float.

## Function 2: `count_passing(scores, passing_score=60)`

Return how many scores are greater than or equal to `passing_score`.

## Function 3: `score_report(scores)`

Return a dictionary with these keys:

- `"average"`: the average score
- `"passing"`: the number of passing scores using the default passing score
- `"total"`: the total number of scores

Example:

```python
score_report([80, 50, 70])
```

Expected result:

```python
{"average": 66.66666666666667, "passing": 2, "total": 3}
```
