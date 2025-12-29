CREATE TABLE if not EXISTS knowledge_base (
    kb_id SERIAL PRIMARY KEY,
    topic VARCHAR(50) NOT NULL,
    questions_keyboard TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

INSERT INTO knowledge_base (topic, question_keywords, answer)
VALUES
('homepage', 'homepage, main page, home', 'PLACEHOLDER: Welcome to our homepage! Here you can find an overview of our services.'),
('mission', 'mission, purpose, goal', 'PLACEHOLDER: Our mission is to provide exceptional service and value to our customers.'),
('about', 'about, company, info', 'PLACEHOLDER: We are a leading company in our industry with a commitment to excellence.'),
('contact', 'contact, support, help', 'PLACEHOLDER: You can reach us via email at suryas2010@outlook.com'),
('resources', 'resources, tools, features', 'PLACEHOLDER: List resources available on the site.'),
('faqs', 'faqs, questions, help', 'PLACEHOLDER: Frequently Asked Questions will be listed here.'),
('testimonials', 'testimonials, reviews, feedback', 'PLACEHOLDER: Read what our customers have to say about us.'),
('blog', 'blog, articles, news', 'PLACEHOLDER: Check out our latest blog posts and industry news.'),
('services', 'services, offerings, products', 'PLACEHOLDER: Explore the range of services and products we offer.'),
('team', 'team, staff, employees', 'PLACEHOLDER: Meet the dedicated team behind our success.');
