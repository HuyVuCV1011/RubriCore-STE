def average_score(scores):
    return sum(scores) / len(scores) if scores else 0


def count_passing(scores, passing_score=60):
    passing_scores = [score for score in scores if score >= passing_score]
    return len(passing_scores)


def score_report(scores):
    average = average_score(scores)
    passing = count_passing(scores)
    total = len(scores)
    return dict(average=average, passing=passing, total=total)
