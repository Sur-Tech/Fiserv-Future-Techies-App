# nlp/similarity.py
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .preprocessing import clean_text

def compute_similarity(user_text, corpus):
    """
    corpus: list of stored questions
    Returns the index of the most similar question
    """
    texts = [clean_text(t) for t in corpus] + [clean_text(user_text)]
    vectorizer = TfidfVectorizer().fit_transform(texts)
    sim_matrix = cosine_similarity(vectorizer[-1], vectorizer[:-1])
    best_idx = sim_matrix.argmax()
    return best_idx, sim_matrix[0][best_idx]

# Example usage
if __name__ == "__main__":
    corpus = ["what is your mission", "homepage description", "contact info"]
    user_q = "Tell me about your purpose"
    idx, score = compute_similarity(user_q, corpus)
    print(idx, score)
