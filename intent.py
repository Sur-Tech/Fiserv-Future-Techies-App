# nlp/intent_detection.py
from .preprocessing import clean_text

TOPICS = {
    "homepage": ["homepage", "home", "main page"],
    "mission": ["mission", "goal", "purpose"],
    "about": ["about", "company", "info"],
    "contact": ["contact", "support", "help"],
    "resources": ["resources", "tools", "features"],
    "faqs": ["faqs", "questions", "help"],
    "testimonials": ["reviews", "feedback", "testimonials"],
    "blog": ["blog", "articles", "news"],
    "services": ["services", "offerings", "products"],
    "team": ["team", "staff", "employees"]
}

def detect_intent(user_text):
    user_text = clean_text(user_text)
    for topic, keywords in TOPICS.items():
        if any(kw in user_text for kw in keywords):
            return topic
    return "unknown"

# Example usage
if __name__ == "__main__":
    print(detect_intent("Can you tell me your mission?"))
