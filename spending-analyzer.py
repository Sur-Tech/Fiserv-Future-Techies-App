
# Imports & Database Connection

from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np

engine = create_engine(
    "postgresql://username:password@localhost:5432/home_finance"
)


# USER ACTIONS


def log_expense(user_id, category, vendor, amount, payment_method, expense_date):
    """
    User logs their own spending
    """
    query = text("""
        INSERT INTO expenses
        (user_id, category, vendor, amount, payment_method, expense_date)
        VALUES (:user_id, :category, :vendor, :amount, :payment_method, :expense_date)
    """)

    with engine.begin() as conn:
        conn.execute(query, {
            "user_id": user_id,
            "category": category,
            "vendor": vendor,
            "amount": amount,
            "payment_method": payment_method,
            "expense_date": expense_date
        })

    print("✅ Expense logged.")


def set_budget(user_id, category, monthly_limit):
    """
    User sets or updates their monthly budget
    """
    query = text("""
        INSERT INTO budgets (user_id, category, monthly_limit)
        VALUES (:user_id, :category, :monthly_limit)
        ON CONFLICT (user_id, category)
        DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit
    """)

    with engine.begin() as conn:
        conn.execute(query, {
            "user_id": user_id,
            "category": category,
            "monthly_limit": monthly_limit
        })

    print("✅ Budget set/updated.")


# MONTHLY SPENDING ANALYSIS


def analyze_month(user_id, month_start):
    """
    Core Household Expense Agent
    """

    # Load monthly expenses
    df = pd.read_sql(
        text("""
            SELECT expense_id, expense_date, category, vendor, amount
            FROM expenses
            WHERE user_id = :user_id
            AND DATE_TRUNC('month', expense_date) = :month
        """),
        engine,
        params={"user_id": user_id, "month": month_start},
        parse_dates=["expense_date"]
    )

    if df.empty:
        print("⚠️ No expenses found for this month.")
        return

    df["day"] = df["expense_date"].dt.day

    
    # Anomaly Detection (Z-score)
    
    mean = df["amount"].mean()
    std = df["amount"].std()

    df["z_score"] = (df["amount"] - mean) / std
    anomalies = df[np.abs(df["z_score"]) > 2]

    with engine.begin() as conn:
        for _, row in anomalies.iterrows():
            conn.execute(
                text("""
                    INSERT INTO spending_alerts
                    (user_id, expense_id, reason, severity)
                    VALUES (:user_id, :expense_id, :reason, :severity)
                """),
                {
                    "user_id": user_id,
                    "expense_id": int(row["expense_id"]),
                    "reason": "Abnormal spending detected",
                    "severity": "HIGH"
                }
            )

    
    # Budget Check
    
    budget_df = pd.read_sql(
        text("""
            SELECT e.category,
                   SUM(e.amount) AS spent,
                   b.monthly_limit
            FROM expenses e
            JOIN budgets b
              ON e.user_id = b.user_id
             AND e.category = b.category
            WHERE e.user_id = :user_id
              AND DATE_TRUNC('month', e.expense_date) = :month
            GROUP BY e.category, b.monthly_limit
        """),
        engine,
        params={"user_id": user_id, "month": month_start}
    )

    with engine.begin() as conn:
        for _, row in budget_df.iterrows():
            if row["spent"] > row["monthly_limit"]:
                conn.execute(
                    text("""
                        INSERT INTO spending_alerts
                        (user_id, reason, severity)
                        VALUES (:user_id, :reason, :severity)
                    """),
                    {
                        "user_id": user_id,
                        "reason": f"Budget exceeded for {row['category']}",
                        "severity": "CRITICAL"
                    }
                )

    
    # Summary Output
    
    summary = {
        "total_spent": float(df["amount"].sum()),
        "average_daily_spend": float(df.groupby("day")["amount"].sum().mean()),
        "top_category": df.groupby("category")["amount"].sum().idxmax(),
        "anomalies_detected": len(anomalies)
    }

    print("📊 Monthly Summary")
    print(summary)


# DAILY SPEND DATA (FOR ML)


def get_daily_spend(user_id):
    """
    Data source for TensorFlow forecasting
    """
    daily_spend = pd.read_sql(
        text("""
            SELECT expense_date, SUM(amount) AS total
            FROM expenses
            WHERE user_id = :user_id
            GROUP BY expense_date
            ORDER BY expense_date
        """),
        engine,
        params={"user_id": user_id},
        parse_dates=["expense_date"]
    )

    return daily_spend["total"].values.reshape(-1, 1)


# EXAMPLE USAGE

if __name__ == "__main__":

    USER_ID = 1

    # User actions
    set_budget(USER_ID, "Groceries", 500)
    set_budget(USER_ID, "Utilities", 300)

    log_expense(USER_ID, "Groceries", "Costco", 82.40, "Debit", "2025-11-18")
    log_expense(USER_ID, "Utilities", "Electric Co", 140.00, "Credit", "2025-11-20")

    # Run monthly analysis
    analyze_month(USER_ID, "2025-11-01")

    # ML-ready data
    values = get_daily_spend(USER_ID)
