# nlp/answer_selector.py
from .intent_detection import detect_intent
from .similarity import compute_similarity

def select_answer(user_question, questions, answers):
    intent = detect_intent(user_question)
    filtered_qs = [q for q, a in zip(questions, answers) if intent in q.lower()]
    if not filtered_qs:
        filtered_qs = questions  # fallback to all
    idx, score = compute_similarity(user_question, filtered_qs)
    return answers[idx], intent, score

# Example usage
if __name__ == "__main__":
    questions = ["What is your mission?", "Tell me about the homepage", "How to contact you?"]
    answers = ["Our mission is...", "Welcome to the homepage", "Email us at ..."]
    ans, intent, score = select_answer("Tell me your purpose", questions, answers)
    print(ans, intent, score)
