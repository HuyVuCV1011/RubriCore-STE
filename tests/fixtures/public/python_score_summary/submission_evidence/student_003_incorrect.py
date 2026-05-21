def average_score(scores):
    return sum(scores)


def count_passing(scores, passing_score=60):
    return len(scores)


def score_report(scores):
    return {
        "average": average_score(scores),
        "passing": count_passing(scores),
    }
