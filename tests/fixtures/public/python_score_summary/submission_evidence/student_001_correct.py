def average_score(scores):
    if len(scores) == 0:
        return 0
    return sum(scores) / len(scores)


def count_passing(scores, passing_score=60):
    count = 0
    for score in scores:
        if score >= passing_score:
            count += 1
    return count


def score_report(scores):
    return {
        "average": average_score(scores),
        "passing": count_passing(scores),
        "total": len(scores),
    }
