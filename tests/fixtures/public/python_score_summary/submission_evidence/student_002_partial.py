def average_score(scores):
    if not scores:
        return 0
    return sum(scores) / len(scores)


def count_passing(scores, passing_score=60):
    total = 0
    for score in scores:
        if score > passing_score:
            total += 1
    return total


def score_report(scores):
    return {
        "average": average_score(scores),
        "passing": count_passing(scores),
        "total": len(scores),
    }
