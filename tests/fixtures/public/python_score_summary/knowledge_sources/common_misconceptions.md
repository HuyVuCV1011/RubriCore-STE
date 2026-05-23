# Common Misconceptions

These synthetic examples describe mistakes that may appear in student submissions.

## Passing Threshold

Some learners use `score > threshold` instead of `score >= threshold`.

This should be treated as a correctness issue because a score exactly equal to the threshold should pass.

## Average Calculation

Some learners divide by a fixed number instead of the number of submitted scores.

This should be treated as incorrect because the function must work for any non-empty list.

## Empty Score Lists

Some learners allow division by zero when the score list is empty.

The expected behavior is to return `0` for the average of an empty list.

## Report Shape

Some learners return a tuple or string summary instead of a dictionary.

The expected report should include `average`, `passing`, and `total` keys.
