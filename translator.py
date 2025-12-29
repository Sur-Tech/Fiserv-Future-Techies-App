# Used Google Translate API to translate text between languages
from langdetect import detect
from googletrans import Translator

translator = Translator()

def translate_to_en(text):
    if detect(text) != 'en':
        return translator.translate(text, dest='en').text
    return text
