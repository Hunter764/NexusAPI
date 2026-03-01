"""
Analysis service — performs text analysis for the /api/analyse endpoint.
"""


from textblob import TextBlob

def analyse_text(text: str) -> dict:
    """
    Perform text analysis: semantic sentiment mapping, word count, and unique word count.

    Args:
        text: Input text string.

    Returns:
        Dict with sentiment, word_count, and unique_word_count.
    """
    # Calculate word statistics
    words = text.split()
    word_count = len(words)
    unique_words = len(set(w.lower().strip(".,!?;:\"'()[]{}") for w in words))

    # Calculate Sentiment Polarity [-1.0 to 1.0]
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    
    # Map polarity to a human-readable sentiment
    if polarity > 0.05:
        sentiment = "Positive"
    elif polarity < -0.05:
        sentiment = "Negative"
    else:
        sentiment = "Neutral"

    return {
        "sentiment": sentiment,
        "word_count": word_count,
        "unique_word_count": unique_words,
    }


def summarise_text(text: str) -> dict:
    """
    Perform text summarisation (simulated).
    In production, this would call an AI model.

    Args:
        text: Input text string.

    Returns:
        Dict with summary result.
    """
    words = text.split()
    word_count = len(words)

    # Simple extractive summary: take first few sentences
    sentences = text.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if s.strip()]
    summary_sentences = sentences[:2] if len(sentences) > 2 else sentences
    summary = ". ".join(summary_sentences) + "." if summary_sentences else text[:100]

    return {
        "summary": summary,
        "original_word_count": word_count,
        "summary_word_count": len(summary.split()),
    }
