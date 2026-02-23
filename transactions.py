import os
import json
import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

import google.generativeai as genai
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from dotenv import load_dotenv

# -----------------------------------------------------------------------
# Plaid imports
# -----------------------------------------------------------------------
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid.exceptions import ApiException
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

# -----------------------------------------------------------------------
# Load env
# -----------------------------------------------------------------------
load_dotenv()

# -----------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_cash_manager")

# -----------------------------------------------------------------------
# Gemini AI Setup
# -----------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not set — AI reports will be disabled.")
    gemini_model = None
else:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("Gemini AI ready.")

# -----------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------
app = Flask(__name__)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# -----------------------------------------------------------------------
# Plaid Config
# -----------------------------------------------------------------------
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET    = os.getenv("PLAID_SECRET")
PLAID_ENV       = os.getenv("PLAID_ENV", "sandbox")

PLAID_HOSTS = {
    "sandbox":     "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production":  "https://production.plaid.com",
}

if PLAID_ENV not in PLAID_HOSTS:
    raise ValueError(f"Invalid PLAID_ENV '{PLAID_ENV}'. Must be one of: {list(PLAID_HOSTS)}")

SIMULATION_MODE = not (PLAID_CLIENT_ID and PLAID_SECRET)

if SIMULATION_MODE:
    logger.warning("Plaid credentials not found — running in SIMULATION MODE.")
else:
    configuration = Configuration(
        host=PLAID_HOSTS[PLAID_ENV],
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret":   PLAID_SECRET,
        }
    )
    api_client   = ApiClient(configuration)
    plaid_client = plaid_api.PlaidApi(api_client)

# -----------------------------------------------------------------------
# Auth Guard
# -----------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            logger.warning("API_KEY not set — authentication is DISABLED")
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Missing Authorization header"}), 401
        token = auth_header.removeprefix("Bearer ").strip()
        if token != API_KEY:
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated

def get_user_id():
    return request.headers.get("X-User-Id", "default_user")

# -----------------------------------------------------------------------
# SQLite — token storage + report history + budgets
# -----------------------------------------------------------------------
DB_PATH = os.getenv("SQLITE_PATH", "plaid_tokens.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        conn = get_db()

        # Plaid access tokens
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plaid_items (
                user_id      TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                item_id      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)

        # Every AI report Gemini generates is saved here
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                report_type  TEXT NOT NULL,
                report_text  TEXT NOT NULL,
                stats_json   TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)

        # Budgets — set by AI automatically or overridden by user
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_budgets (
                user_id       TEXT NOT NULL,
                category      TEXT NOT NULL,
                monthly_limit REAL NOT NULL,
                set_by        TEXT DEFAULT 'ai',
                updated_at    TEXT NOT NULL,
                PRIMARY KEY (user_id, category)
            )
        """)

        conn.commit()

# -----------------------------------------------------------------------
# Token helpers
# -----------------------------------------------------------------------
def save_token(user_id, access_token, item_id):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute("""
        INSERT INTO plaid_items (user_id, access_token, item_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            access_token = excluded.access_token,
            item_id      = excluded.item_id,
            updated_at   = excluded.updated_at
    """, (user_id, access_token, item_id, now, now))
    conn.commit()

def load_token(user_id):
    row = get_db().execute(
        "SELECT access_token, item_id FROM plaid_items WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return (row["access_token"], row["item_id"]) if row else (None, None)

def delete_token(user_id):
    conn = get_db()
    conn.execute("DELETE FROM plaid_items WHERE user_id = ?", (user_id,))
    conn.commit()

# -----------------------------------------------------------------------
# Budget helpers
# -----------------------------------------------------------------------
def save_budget(user_id, category, monthly_limit, set_by="ai"):
    now = datetime.utcnow().isoformat()
    get_db().execute("""
        INSERT INTO user_budgets (user_id, category, monthly_limit, set_by, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, category) DO UPDATE SET
            monthly_limit = excluded.monthly_limit,
            set_by        = excluded.set_by,
            updated_at    = excluded.updated_at
    """, (user_id, category, monthly_limit, set_by, now))
    get_db().commit()

def load_budgets(user_id):
    rows = get_db().execute(
        "SELECT category, monthly_limit, set_by FROM user_budgets WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    return {
        row["category"]: {"limit": row["monthly_limit"], "set_by": row["set_by"]}
        for row in rows
    }

def save_report(user_id, report_type, report_text, stats):
    now = datetime.utcnow().isoformat()
    get_db().execute("""
        INSERT INTO ai_reports (user_id, report_type, report_text, stats_json, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, report_type, report_text, json.dumps(stats), now))
    get_db().commit()

def load_report_history(user_id, limit=5):
    rows = get_db().execute("""
        SELECT id, report_type, report_text, stats_json, created_at
        FROM ai_reports WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    return [
        {
            "id":         row["id"],
            "type":       row["report_type"],
            "report":     row["report_text"],
            "stats":      json.loads(row["stats_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]

# -----------------------------------------------------------------------
# Plaid error handler
# -----------------------------------------------------------------------
def handle_plaid_exception(e):
    try:
        body = json.loads(e.body)
    except Exception:
        body = {}
    error_code    = body.get("error_code", "UNKNOWN")
    error_message = body.get("error_message", str(e))
    error_type    = body.get("error_type", "API_ERROR")
    logger.error("Plaid API error: type=%s code=%s message=%s", error_type, error_code, error_message)
    status_map = {
        "ITEM_LOGIN_REQUIRED":  401,
        "INVALID_ACCESS_TOKEN": 401,
        "INVALID_PUBLIC_TOKEN": 400,
        "RATE_LIMIT_EXCEEDED":  429,
        "INSTITUTION_DOWN":     503,
    }
    return jsonify({
        "success":         False,
        "error":           error_message,
        "error_code":      error_code,
        "error_type":      error_type,
        "requires_reauth": error_code == "ITEM_LOGIN_REQUIRED",
    }), status_map.get(error_code, 502)

# -----------------------------------------------------------------------
# Input validation
# -----------------------------------------------------------------------
def validate_int_param(value, default=30, min_val=0, max_val=730):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default, None
    if not (min_val <= v <= max_val):
        return None, f"Value must be between {min_val} and {max_val}"
    return v, None

# -----------------------------------------------------------------------
# Fake data generators
# -----------------------------------------------------------------------
def generate_fake_accounts():
    return [
        {
            "account_id": "fake_checking_001",
            "balances": {"available": 2500.50, "current": 2500.50, "limit": None, "iso_currency_code": "USD"},
            "mask": "4321", "name": "Plaid Checking",
            "official_name": "Plaid Silver Standard 0.1% Interest Checking",
            "subtype": "checking", "type": "depository"
        },
        {
            "account_id": "fake_savings_001",
            "balances": {"available": 10000.00, "current": 10000.00, "limit": None, "iso_currency_code": "USD"},
            "mask": "5678", "name": "Plaid Saving",
            "official_name": "Plaid Bronze Standard 0.2% Interest Saving",
            "subtype": "savings", "type": "depository"
        },
        {
            "account_id": "fake_credit_001",
            "balances": {"available": 3500.00, "current": 1500.00, "limit": 5000, "iso_currency_code": "USD"},
            "mask": "9012", "name": "Plaid Credit Card",
            "official_name": "Plaid Diamond 12.5% APR Interest Credit Card",
            "subtype": "credit card", "type": "credit"
        },
    ]

def generate_fake_transactions(days=30, num_transactions=90):
    merchants_by_category = {
        "Food and Drink":    [("Starbucks",4.5,8),("McDonald's",8,15),("Chipotle",10,18),("Whole Foods",30,120),("Trader Joe's",25,80),("Pizza Hut",15,35),("Subway",7,12)],
        "Transportation":    [("Uber",8,35),("Lyft",7,30),("Shell Gas Station",30,60),("Chevron",35,65),("Parking Meter",2,10),("Public Transit",2.5,5)],
        "Shopping":          [("Amazon",10,200),("Target",15,150),("Walmart",20,180),("Best Buy",25,500),("Nike Store",50,200),("Apple Store",20,2000)],
        "Entertainment":     [("Netflix",15.99,15.99),("Spotify",9.99,9.99),("AMC Theaters",12,30),("Steam Games",5,60),("PlayStation Store",10,70)],
        "Bills & Utilities": [("Electric Company",80,150),("Internet Provider",59.99,59.99),("Water Company",30,50),("Phone Bill",45,85),("Insurance",100,200)],
        "Healthcare":        [("CVS Pharmacy",10,50),("Walgreens",8,45),("Doctor's Office",25,200),("Dentist",50,300)],
        "Transfer":          [("Venmo",10,100),("PayPal",5,200),("Zelle Payment",20,150)],
    }
    transactions = []
    for i in range(num_transactions):
        days_ago         = random.randint(0, days)
        transaction_date = datetime.now() - timedelta(days=days_ago)
        category         = random.choice(list(merchants_by_category.keys()))
        merchant_name, min_amt, max_amt = random.choice(merchants_by_category[category])
        amount           = round(random.uniform(min_amt, max_amt), 2)
        pending          = days_ago <= 2 and random.random() < 0.3
        transactions.append({
            "transaction_id":    f"fake_tx_{i:04d}",
            "account_id":        random.choice(["fake_checking_001", "fake_credit_001"]),
            "amount":            amount,
            "iso_currency_code": "USD",
            "category":          [category],
            "date":              transaction_date.strftime("%Y-%m-%d"),
            "authorized_date":   transaction_date.strftime("%Y-%m-%d"),
            "name":              merchant_name.upper(),
            "merchant_name":     merchant_name,
            "payment_channel":   random.choice(["in store", "online", "other"]),
            "pending":           pending,
            "transaction_type":  "place",
        })
    return sorted(transactions, key=lambda x: x["date"], reverse=True)

# -----------------------------------------------------------------------
# Core stats calculator — pure math, feeds Gemini with clean numbers
# -----------------------------------------------------------------------
def calculate_stats(transactions):
    if not transactions:
        return None

    total_spent    = 0.0
    total_income   = 0.0
    categories     = {}
    merchants      = {}
    daily_spending = {}

    for tx in transactions:
        amount   = tx["amount"]
        date     = tx["date"]
        merchant = tx.get("merchant_name") or tx.get("name", "Unknown")

        if amount > 0:
            total_spent += amount
        else:
            total_income += abs(amount)

        category = (
            tx["category"][0] if isinstance(tx.get("category"), list) and tx["category"]
            else tx.get("category", "Other") or "Other"
        )
        categories[category] = categories.get(category, 0.0) + amount

        if merchant not in merchants:
            merchants[merchant] = {"count": 0, "total": 0.0}
        merchants[merchant]["count"] += 1
        merchants[merchant]["total"] += amount

        daily_spending[date] = daily_spending.get(date, 0.0) + amount

    avg_daily    = round(total_spent / len(daily_spending), 2) if daily_spending else 0
    sorted_cats  = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    top_merchants = sorted(
        [(m, d["count"], d["total"]) for m, d in merchants.items()],
        key=lambda x: x[1], reverse=True
    )[:5]

    return {
        "total_spent":         round(total_spent, 2),
        "total_income":        round(total_income, 2),
        "net_cash_flow":       round(total_income - total_spent, 2),
        "transaction_count":   len(transactions),
        "avg_daily_spend":     avg_daily,
        "avg_transaction":     round(total_spent / len(transactions), 2) if transactions else 0,
        "category_breakdown":  {c: round(a, 2) for c, a in sorted_cats},
        "top_category":        sorted_cats[0][0] if sorted_cats else None,
        "top_category_amount": round(sorted_cats[0][1], 2) if sorted_cats else 0,
        "top_merchants":       [{"name": m[0], "visits": m[1], "total": round(m[2], 2)} for m in top_merchants],
        "biggest_expense_day": max(daily_spending.items(), key=lambda x: x[1])[0] if daily_spending else None,
    }

# -----------------------------------------------------------------------
# GEMINI AI — Personal Financial Advisor
# Gemini acts as the user's CFO: writes reports, sets budgets,
# sends alerts, and answers financial questions.
# -----------------------------------------------------------------------

def gemini_generate(prompt: str) -> str:
    """Send a prompt to Gemini and return the text response."""
    if not gemini_model:
        return "AI unavailable — set GEMINI_API_KEY in your .env file."
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error("Gemini error: %s", e)
        return f"AI temporarily unavailable: {str(e)}"


def gemini_spending_report(stats: dict, budgets: dict, period_days: int) -> str:
    """
    Gemini writes a full personalised financial health report.
    It acts as a personal CFO speaking directly to the user.
    """
    budget_text = "\n".join(
        [f"  - {cat}: ${info['limit']:.2f}/month (set by {info['set_by']})"
         for cat, info in budgets.items()]
    ) or "  No budgets set yet."

    cat_text = "\n".join(
        [f"  - {cat}: ${amt:.2f}" for cat, amt in stats["category_breakdown"].items()]
    )

    merchant_text = "\n".join(
        [f"  - {m['name']}: {m['visits']} visits, ${m['total']:.2f} total"
         for m in stats["top_merchants"]]
    )

    prompt = f"""
You are CashLens AI, a personal financial advisor writing a report directly to the user.
Be warm, direct, and specific. Use actual dollar amounts from their data.
Do NOT give generic advice — reference THEIR specific spending habits.
Use clear sections with emoji headers. Keep it under 400 words.

THEIR SPENDING DATA — last {period_days} days:

SUMMARY:
  - Total spent: ${stats['total_spent']:.2f}
  - Total income recorded: ${stats['total_income']:.2f}
  - Net cash flow: ${stats['net_cash_flow']:.2f}
  - Number of transactions: {stats['transaction_count']}
  - Average daily spend: ${stats['avg_daily_spend']:.2f}
  - Biggest spending day: {stats['biggest_expense_day']}

SPENDING BY CATEGORY:
{cat_text}

TOP MERCHANTS VISITED:
{merchant_text}

CURRENT BUDGETS:
{budget_text}

Write a report that:
1. Opens with a one-line verdict on their financial health
2. Names exactly what they spent the most on and whether that is a concern
3. Calls out any categories where they blew their budget
4. Gives 3 specific, actionable things they should do THIS WEEK
5. Ends with a short encouraging note
"""
    return gemini_generate(prompt)


def gemini_budget_recommendations(stats: dict) -> dict:
    """
    Gemini recommends monthly budget limits for each category
    based on the user's actual spending. Returns {category: limit}.
    """
    cat_text = "\n".join(
        [f"  - {cat}: ${amt:.2f} over the period"
         for cat, amt in stats["category_breakdown"].items()]
    )

    prompt = f"""
You are a personal AI financial advisor.
Based on this user's real spending, recommend sensible monthly budgets for each category.

Their spending:
{cat_text}

Average daily spend: ${stats['avg_daily_spend']:.2f}
Net cash flow: ${stats['net_cash_flow']:.2f}

Rules:
- If net cash flow is negative (overspending), cut budgets 10-20% below current spend
- If net cash flow is positive (saving), set budgets close to current spend
- Only include categories from the data above
- Never cut any budget by more than 30% at once

Respond ONLY with valid JSON — no explanation, no markdown code fences:
{{"Food and Drink": 400, "Transportation": 150}}
"""
    raw = gemini_generate(prompt)
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception:
        logger.warning("Could not parse Gemini budget JSON: %s", raw)
        return {}


def gemini_alert(stats: dict, budgets: dict) -> str:
    """
    Gemini checks spending vs budgets and writes an urgent alert
    if the user is overspending in any category.
    """
    over_budget = []
    for cat, spent in stats["category_breakdown"].items():
        if cat in budgets:
            limit = budgets[cat]["limit"]
            if spent > limit:
                over_budget.append({
                    "category": cat,
                    "spent":    round(spent, 2),
                    "limit":    limit,
                    "over_by":  round(spent - limit, 2)
                })

    if not over_budget and stats["net_cash_flow"] >= 0:
        return "✅ All budgets on track! You're managing your money well this period."

    over_text = "\n".join(
        [f"  - {o['category']}: spent ${o['spent']:.2f} vs limit ${o['limit']:.2f} (over by ${o['over_by']:.2f})"
         for o in over_budget]
    ) or "  No individual category overages."

    prompt = f"""
You are CashLens AI sending an urgent but caring spending alert to a user.
Be specific, direct, and helpful. Under 150 words. Use emoji.

OVERSPENT CATEGORIES:
{over_text}

NET CASH FLOW: ${stats['net_cash_flow']:.2f} ({'NEGATIVE — spending more than earning!' if stats['net_cash_flow'] < 0 else 'positive'})

Write a short alert that:
1. Directly names which categories they overspent in and by how much
2. If overall cash flow is negative, flag that clearly
3. Gives one concrete action they can take TODAY to fix it
"""
    return gemini_generate(prompt)


def gemini_chat(user_message: str, stats: dict, budgets: dict) -> str:
    """
    User can ask Gemini anything about their finances.
    Gemini has full context of their actual spending data.
    """
    cat_text = "\n".join(
        [f"  - {cat}: ${amt:.2f}" for cat, amt in stats["category_breakdown"].items()]
    )
    budget_text = "\n".join(
        [f"  - {cat}: ${info['limit']:.2f}/month" for cat, info in budgets.items()]
    ) or "  No budgets set."

    prompt = f"""
You are CashLens AI, a friendly personal financial advisor.
Answer the user's question using their actual spending data below.
Be conversational and specific. Under 200 words.

USER'S DATA:
- Total spent: ${stats['total_spent']:.2f}
- Net cash flow: ${stats['net_cash_flow']:.2f}
- Avg daily spend: ${stats['avg_daily_spend']:.2f}
- Top category: {stats['top_category']} (${stats['top_category_amount']:.2f})

SPENDING BY CATEGORY:
{cat_text}

THEIR BUDGETS:
{budget_text}

USER'S QUESTION: {user_message}
"""
    return gemini_generate(prompt)

# -----------------------------------------------------------------------
# Internal helper — fetch all Plaid transactions with full pagination
# -----------------------------------------------------------------------
def _fetch_all_transactions(access_token, days):
    try:
        end_date   = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        first_resp = plaid_client.transactions_get(
            TransactionsGetRequest(
                access_token=access_token, start_date=start_date, end_date=end_date,
                options=TransactionsGetRequestOptions(count=500, offset=0),
            )
        )
        all_tx = list(first_resp["transactions"])
        total  = first_resp["total_transactions"]
        while len(all_tx) < total:
            resp = plaid_client.transactions_get(
                TransactionsGetRequest(
                    access_token=access_token, start_date=start_date, end_date=end_date,
                    options=TransactionsGetRequestOptions(count=500, offset=len(all_tx)),
                )
            )
            fetched = list(resp["transactions"])
            if not fetched:
                break
            all_tx.extend(fetched)
        return [dict(tx) for tx in all_tx]
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Error fetching transactions")
        return jsonify({"success": False, "error": "Internal server error"}), 500

# -----------------------------------------------------------------------
# Routes — Plaid
# -----------------------------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "app":     "CashLens AI — Flask + Plaid + Gemini",
        "version": "3.0",
        "endpoints": [
            "POST /create_link_token  — Start Plaid bank connection",
            "POST /exchange_token     — Complete bank connection",
            "GET  /accounts           — View bank accounts",
            "GET  /transactions       — View transactions + stats",
            "GET  /report             — Full AI financial health report",
            "GET  /alert              — AI budget overspend alert",
            "POST /budgets/auto       — AI sets your budgets automatically",
            "POST /budgets/set        — Manually set a budget",
            "GET  /budgets            — View current budgets",
            "POST /chat               — Ask AI anything about your finances",
            "GET  /history            — Past AI reports",
            "POST /simulate           — Generate test data",
            "POST /reset              — Disconnect bank",
        ],
    })


@app.route("/create_link_token", methods=["POST"])
@require_auth
def create_link_token():
    user_id = get_user_id()
    if SIMULATION_MODE:
        return jsonify({"success": True, "link_token": "fake-link-token-for-testing", "simulation_mode": True})
    try:
        req = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="CashLens AI",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = plaid_client.link_token_create(req)
        return jsonify({"success": True, "link_token": response["link_token"]})
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /create_link_token")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/exchange_token", methods=["POST"])
@require_auth
def exchange_token():
    user_id      = get_user_id()
    public_token = (request.json or {}).get("public_token")
    if not public_token:
        return jsonify({"success": False, "error": "Missing public_token"}), 400
    if SIMULATION_MODE or public_token == "fake-public-token":
        save_token(user_id, "fake-access-token", "fake-item-id")
        return jsonify({"success": True, "message": "Bank connected (simulation mode)", "simulation_mode": True})
    try:
        response = plaid_client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        save_token(user_id, response["access_token"], response["item_id"])
        return jsonify({"success": True, "message": "Bank connected successfully"})
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /exchange_token")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/accounts", methods=["GET"])
@require_auth
def get_accounts():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    if SIMULATION_MODE or access_token == "fake-access-token":
        return jsonify({"success": True, "accounts": generate_fake_accounts(), "simulation_mode": True})
    if not access_token:
        return jsonify({"success": False, "error": "Bank not connected"}), 400
    try:
        response = plaid_client.accounts_get(AccountsGetRequest(access_token=access_token))
        return jsonify({"success": True, "accounts": [dict(a) for a in response["accounts"]]})
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /accounts")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/transactions", methods=["GET"])
@require_auth
def get_transactions():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    days, err = validate_int_param(request.args.get("days", 30), default=30, min_val=1, max_val=730)
    if err:
        return jsonify({"success": False, "error": err}), 400
    page_size, err = validate_int_param(request.args.get("page_size", 20), default=20, min_val=1, max_val=500)
    if err:
        return jsonify({"success": False, "error": err}), 400
    offset, err = validate_int_param(request.args.get("offset", 0), default=0, min_val=0, max_val=100_000)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if SIMULATION_MODE or access_token == "fake-access-token":
        all_tx = generate_fake_transactions(days=days, num_transactions=90)
        stats  = calculate_stats(all_tx)
        page   = all_tx[offset: offset + page_size]
        return jsonify({
            "success": True, "transactions": page,
            "total_transactions": len(all_tx),
            "offset": offset, "page_size": page_size,
            "has_more": (offset + page_size) < len(all_tx),
            "stats": stats, "simulation_mode": True,
        })

    if not access_token:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    try:
        all_tx = _fetch_all_transactions(access_token, days)
        if isinstance(all_tx, tuple):
            return all_tx
        stats = calculate_stats(all_tx)
        page  = all_tx[offset: offset + page_size]
        return jsonify({
            "success": True, "transactions": page,
            "total_transactions": len(all_tx),
            "offset": offset, "page_size": page_size,
            "has_more": (offset + page_size) < len(all_tx),
            "stats": stats,
        })
    except Exception:
        logger.exception("Unexpected error in /transactions")
        return jsonify({"success": False, "error": "Internal server error"}), 500

# -----------------------------------------------------------------------
# Routes — Gemini AI
# -----------------------------------------------------------------------

@app.route("/report", methods=["GET"])
@require_auth
def get_report():
    """
    Gemini reads the user's transactions and writes a full
    personalised financial health report saved to history.
    """
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    days, err = validate_int_param(request.args.get("days", 30), default=30, min_val=1, max_val=730)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if SIMULATION_MODE or access_token == "fake-access-token":
        all_tx = generate_fake_transactions(days=days, num_transactions=90)
    elif access_token:
        all_tx = _fetch_all_transactions(access_token, days)
        if isinstance(all_tx, tuple):
            return all_tx
    else:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    stats       = calculate_stats(all_tx)
    budgets     = load_budgets(user_id)
    report_text = gemini_spending_report(stats, budgets, days)

    save_report(user_id, "full_report", report_text, stats)

    return jsonify({
        "success":      True,
        "report":       report_text,
        "stats":        stats,
        "period_days":  days,
        "generated_at": datetime.utcnow().isoformat(),
    })


@app.route("/alert", methods=["GET"])
@require_auth
def get_alert():
    """
    Gemini checks spending vs budgets and sends an alert
    if the user is overspending in any category.
    """
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    days, err = validate_int_param(request.args.get("days", 30), default=30, min_val=1, max_val=730)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if SIMULATION_MODE or access_token == "fake-access-token":
        all_tx = generate_fake_transactions(days=days, num_transactions=90)
    elif access_token:
        all_tx = _fetch_all_transactions(access_token, days)
        if isinstance(all_tx, tuple):
            return all_tx
    else:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    stats      = calculate_stats(all_tx)
    budgets    = load_budgets(user_id)
    alert_text = gemini_alert(stats, budgets)

    save_report(user_id, "alert", alert_text, stats)

    return jsonify({
        "success": True,
        "alert":   alert_text,
        "budgets": budgets,
        "stats_summary": {
            "total_spent":   stats["total_spent"],
            "net_cash_flow": stats["net_cash_flow"],
        },
    })


@app.route("/budgets/auto", methods=["POST"])
@require_auth
def auto_set_budgets():
    """
    Gemini analyses spending and automatically sets smart monthly
    budgets for every category — acting as the user's personal CFO.
    """
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    days, err = validate_int_param((request.json or {}).get("days", 30), default=30, min_val=1, max_val=730)
    if err:
        return jsonify({"success": False, "error": err}), 400

    if SIMULATION_MODE or access_token == "fake-access-token":
        all_tx = generate_fake_transactions(days=days, num_transactions=90)
    elif access_token:
        all_tx = _fetch_all_transactions(access_token, days)
        if isinstance(all_tx, tuple):
            return all_tx
    else:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    stats       = calculate_stats(all_tx)
    recommended = gemini_budget_recommendations(stats)

    if not recommended:
        return jsonify({"success": False, "error": "AI could not generate budgets. Try again."}), 500

    for category, limit in recommended.items():
        save_budget(user_id, category, float(limit), set_by="ai")

    return jsonify({
        "success": True,
        "message": "AI has set your budgets based on your spending patterns.",
        "budgets": recommended,
    })


@app.route("/budgets/set", methods=["POST"])
@require_auth
def set_budget_manual():
    """User manually sets or overrides a budget for a specific category."""
    user_id  = get_user_id()
    body     = request.json or {}
    category = body.get("category")
    limit    = body.get("monthly_limit")

    if not category or limit is None:
        return jsonify({"success": False, "error": "Missing category or monthly_limit"}), 400
    try:
        limit = float(limit)
        if limit < 0:
            raise ValueError
    except ValueError:
        return jsonify({"success": False, "error": "monthly_limit must be a positive number"}), 400

    save_budget(user_id, category, limit, set_by="user")
    return jsonify({"success": True, "message": f"Budget for '{category}' set to ${limit:.2f}/month"})


@app.route("/budgets", methods=["GET"])
@require_auth
def get_budgets():
    """Return all current budgets for the user."""
    user_id = get_user_id()
    return jsonify({"success": True, "budgets": load_budgets(user_id)})


@app.route("/chat", methods=["POST"])
@require_auth
def chat():
    """
    User asks Gemini anything about their finances.
    Gemini has full context of their real spending data and budgets.
    """
    user_id  = get_user_id()
    body     = request.json or {}
    message  = body.get("message", "").strip()

    if not message:
        return jsonify({"success": False, "error": "Missing message"}), 400

    access_token, _ = load_token(user_id)

    if SIMULATION_MODE or access_token == "fake-access-token":
        all_tx = generate_fake_transactions(days=30, num_transactions=90)
    elif access_token:
        all_tx = _fetch_all_transactions(access_token, 30)
        if isinstance(all_tx, tuple):
            return all_tx
    else:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    stats   = calculate_stats(all_tx)
    budgets = load_budgets(user_id)
    reply   = gemini_chat(message, stats, budgets)

    return jsonify({"success": True, "reply": reply, "message": message})


@app.route("/history", methods=["GET"])
@require_auth
def get_history():
    """Return past AI reports for the user."""
    user_id = get_user_id()
    limit, err = validate_int_param(request.args.get("limit", 5), default=5, min_val=1, max_val=50)
    if err:
        return jsonify({"success": False, "error": err}), 400
    history = load_report_history(user_id, limit=limit)
    return jsonify({"success": True, "history": history, "count": len(history)})


@app.route("/simulate", methods=["POST"])
@require_auth
def simulate():
    user_id = get_user_id()
    body    = request.json or {}
    days_val, err = validate_int_param(body.get("days", 30), default=30, min_val=1, max_val=730)
    if err:
        return jsonify({"success": False, "error": err}), 400
    num_tx_val, err = validate_int_param(body.get("num_transactions", 90), default=90, min_val=1, max_val=500)
    if err:
        return jsonify({"success": False, "error": err}), 400
    save_token(user_id, "fake-access-token", "fake-item-id")
    fake_tx = generate_fake_transactions(days=days_val, num_transactions=num_tx_val)
    return jsonify({"success": True, "message": "Simulation data generated", "stats": {"accounts": 3, "transactions": len(fake_tx)}})


@app.route("/reset", methods=["POST"])
@require_auth
def reset():
    delete_token(get_user_id())
    return jsonify({"success": True, "message": "Bank disconnected"})

# -----------------------------------------------------------------------
# Error handlers
# -----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_e):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"success": False, "error": "Method not allowed"}), 405

@app.errorhandler(500)
def server_error(_e):
    return jsonify({"success": False, "error": "Internal server error"}), 500

# -----------------------------------------------------------------------
# Startup
# -----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  CashLens AI — Flask + Plaid + Gemini  v3.0")
    print("=" * 60)
    print(f"  Plaid environment : {PLAID_ENV}")
    print(f"  Simulation mode   : {SIMULATION_MODE}")
    print(f"  Gemini AI         : {'Ready ✅' if gemini_model else 'Disabled ⚠️  (set GEMINI_API_KEY)'}")
    print(f"  Auth              : {'API_KEY set ✅' if API_KEY else 'DISABLED ⚠️'}")
    print(f"  Token storage     : {DB_PATH}")
    print("=" * 60)
    app.run(debug=(PLAID_ENV == "sandbox"), port=5000)
