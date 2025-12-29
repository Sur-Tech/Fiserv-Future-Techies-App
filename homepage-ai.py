# homepage_ai_sql.py
from sqlalchemy import create_engine, text


# Database connection

# Replace 'username' and 'password' with your PostgreSQL credentials
engine = create_engine("postgresql://username:password@localhost:5432/home_finance")


# Core function to query SQL

def get_homepage_answer(user_question):
    """
    Queries the knowledge_base SQL table for homepage topics.
    Returns the answer for a question containing relevant keywords.
    """
    user_question_lower = user_question.lower()
    
    query = text("""
        SELECT topic, questions_keyboard, answer
        FROM knowledge_base
        WHERE topic IN (
            'homepage', 'mission', 'about', 'contact', 'resources',
            'faqs', 'testimonials', 'blog', 'services', 'team'
        )
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query).fetchall()
    
    for row in results:
        # Split keywords and strip spaces
        keywords = [k.strip().lower() for k in row['questions_keyboard'].split(',')]
        if any(kw in user_question_lower for kw in keywords):
            return row['answer']
    
    return "Sorry, I don't have information about that part of the homepage yet."


# Example interactive usage

if __name__ == "__main__":
    print("Homepage AI (type 'exit' to quit)")
    while True:
        user_q = input("Ask a question: ")
        if user_q.lower() in ["exit", "quit"]:
            break
        answer = get_homepage_answer(user_q)
        print("Answer:", answer)
