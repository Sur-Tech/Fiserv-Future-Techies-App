# nlp/keyword_extraction.py
from sklearn.feature_extraction.text import CountVectorizer
from .preprocessing import clean_text

def extract_keywords(text, max_keywords=5):
    text = clean_text(text)
    vectorizer = CountVectorizer(stop_words='english', max_features=max_keywords)
    X = vectorizer.fit_transform([text])
    return vectorizer.get_feature_names_out().tolist()

# Example usage
if __name__ == "__main__":
    print(extract_keywords("Tell me about your mission and goals"))
