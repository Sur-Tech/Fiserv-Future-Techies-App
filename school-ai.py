from sqlalchemy import create_engine, text

engine = create_engine("postgresql://username:password@localhost:5432/home_finance")

def get_school_answer(user_question):
    user_question_lower = user_question.lower()
    
    query = text("""
        SELECT topic, questions_keyboard, answer
        FROM knowledge_base_school
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query).fetchall()
    
    for row in results:
        keywords = [k.strip().lower() for k in row['questions_keyboard'].split(',')]
        if any(kw in user_question_lower for kw in keywords):
            return row['answer']
    
    return "Sorry, I don't have information about school yet."

if __name__ == "__main__":
    print("School AI (type 'exit' to quit)")
    while True:
        user_q = input("Ask a question: ")
        if user_q.lower() in ["exit", "quit"]:
            break
        answer = get_school_answer(user_q)
        print("Answer:", answer)
