"""
Sentiment analysis for review text.
Uses a lexicon-based approach (no heavy ML dependency) for fast, accurate
sentiment scoring of customer reviews.
"""
from typing import Tuple

POSITIVE_WORDS = {
    "excellent", "outstanding", "amazing", "fantastic", "wonderful", "great",
    "love", "perfect", "best", "brilliant", "superb", "exceptional",
    "recommend", "helpful", "easy", "intuitive", "fast", "reliable",
    "efficient", "effective", "powerful", "seamless", "smooth", "impressed",
    "delighted", "satisfied", "happy", "pleased", "worth", "value",
    "good", "nice", "clean", "simple", "awesome", "solid", "strong",
    "responsive", "professional", "transparent", "honest", "consistent",
}

NEGATIVE_WORDS = {
    "terrible", "awful", "horrible", "worst", "bad", "poor", "disappointing",
    "frustrating", "buggy", "broken", "slow", "expensive", "overpriced",
    "useless", "waste", "missing", "lacking", "difficult", "confusing",
    "unreliable", "inconsistent", "crash", "crashes", "failed", "failure",
    "problem", "issues", "bugs", "glitch", "glitches", "unresponsive",
    "support", "abandoned", "ignore", "ignored", "refused", "lied",
    "scam", "fraud", "hidden", "surprised", "shock", "regret", "canceling",
    "cancel", "switch", "switching", "avoid", "warning", "beware",
}

INTENSIFIERS = {"very", "extremely", "absolutely", "completely", "totally", "really", "quite"}
NEGATORS = {"not", "no", "never", "wasn't", "isn't", "doesn't", "don't", "didn't", "hardly", "barely"}


def analyze_reviews(text: str) -> Tuple[str, float]:
    """
    Returns (sentiment_label, sentiment_score).
    sentiment_label: 'positive', 'negative', or 'neutral'
    sentiment_score: -1.0 (very negative) to +1.0 (very positive)
    """
    if not text:
        return "neutral", 0.0

    words = text.lower().split()
    score = 0.0
    i = 0

    while i < len(words):
        word = words[i].strip(".,!?;:'\"()[]")
        negated = False
        intensified = False

        if i > 0 and words[i - 1].strip(".,!?;:'\"()[]") in NEGATORS:
            negated = True
        if i > 0 and words[i - 1].strip(".,!?;:'\"()[]") in INTENSIFIERS:
            intensified = True
        if i > 1 and words[i - 2].strip(".,!?;:'\"()[]") in NEGATORS:
            negated = True

        weight = 1.5 if intensified else 1.0

        if word in POSITIVE_WORDS:
            score += (-weight if negated else weight)
        elif word in NEGATIVE_WORDS:
            score += (weight if negated else -weight)

        i += 1

    word_count = max(len(words), 1)
    normalized = score / (word_count ** 0.5)
    normalized = max(-1.0, min(1.0, normalized))

    if normalized > 0.1:
        label = "positive"
    elif normalized < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return label, round(normalized, 4)


def extract_keywords(text: str, keywords: list) -> list:
    """Find which alert keywords appear in a review."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def summarize_sentiment(reviews: list) -> dict:
    """Aggregate sentiment stats across a list of reviews."""
    if not reviews:
        return {"average_score": 0.0, "positive_pct": 0, "negative_pct": 0, "neutral_pct": 0}

    scores = [r.get("sentiment_score", 0.0) for r in reviews]
    labels = [r.get("sentiment", "neutral") for r in reviews]
    n = len(reviews)

    return {
        "average_score": round(sum(scores) / n, 4),
        "positive_pct": round(labels.count("positive") / n * 100, 1),
        "negative_pct": round(labels.count("negative") / n * 100, 1),
        "neutral_pct": round(labels.count("neutral") / n * 100, 1),
        "total_reviews": n,
    }
