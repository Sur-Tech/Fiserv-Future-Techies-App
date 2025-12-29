-- Ensure USERS table exists

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(150) UNIQUE
);


-- Ensure EXPENSES supports user logging

ALTER TABLE expenses
ADD COLUMN IF NOT EXISTS user_id INT;

ALTER TABLE expenses
ADD CONSTRAINT fk_expenses_user
FOREIGN KEY (user_id)
REFERENCES users(user_id)
ON DELETE CASCADE;

-- Index for faster per-user queries
CREATE INDEX IF NOT EXISTS idx_expenses_user_date
ON expenses (user_id, expense_date);


-- USER-DEFINED BUDGETS

CREATE TABLE IF NOT EXISTS budgets (
    budget_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    monthly_limit NUMERIC(10,2) NOT NULL CHECK (monthly_limit > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prevent duplicate budgets per user/category
ALTER TABLE budgets
ADD CONSTRAINT unique_user_category
UNIQUE (user_id, category);


-- SPENDING ALERTS (Budget + Anomaly)

CREATE TABLE IF NOT EXISTS spending_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    expense_id INT REFERENCES expenses(expense_id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
