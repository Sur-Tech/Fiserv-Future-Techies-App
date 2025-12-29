# nlp/__init__.py
from .preprocessing import clean_text
from .keyword_extraction import extract_keywords
from .similarity import compute_similarity
from .intent_detection import detect_intent
from .answer_selector import select_answer
from .embedding_model import get_most_similar
from .response_formatter import format_answer
