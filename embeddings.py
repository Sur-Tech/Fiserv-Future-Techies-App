# nlp/embedding_model.py
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer('all-MiniLM-L6-v2')

def get_most_similar(query, corpus):
    embeddings = model.encode(corpus + [query])
    sim = cosine_similarity([embeddings[-1]], embeddings[:-1])
    best_idx = sim.argmax()
    return best_idx, sim[0][best_idx]

# Example usage
if __name__ == "__main__":
    corpus = ["Our mission is...", "Homepage info", "Contact details"]
    idx, score = get_most_similar("Tell me your purpose", corpus)
    print(idx, score)
