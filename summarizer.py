from transformers import pipeline

summarizer = pipeline("summarization")

def summarize(text):
    summary = summarizer(text, max_length=50, min_length=20, do_sample=False)
    return summary[0]['summary_text']
