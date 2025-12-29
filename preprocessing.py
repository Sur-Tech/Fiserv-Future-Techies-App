# nlp/preprocessing.py
import re

def clean_text(text):
    """
    Lowercase, remove punctuation, extra spaces.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Example usage
if __name__ == "__main__":
    sample = "  What is your Mission?  "
    print(clean_text(sample))  # Output: "what is your mission"
