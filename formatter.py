# nlp/response_formatter.py
def format_answer(answer, intent=None, score=None):
    response = f"Answer: {answer}"
    if score:
        response += f" (Confidence: {score:.2f})"
    if intent:
        response += f" [Topic: {intent}]"
    return response

# Example usage
if __name__ == "__main__":
    print(format_answer("Our mission is ...", "mission", 0.92))
