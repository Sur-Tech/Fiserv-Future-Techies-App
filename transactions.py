import os
import json
import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

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
# Logging — structured, never prints raw tokens
# -----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_cash_manager")

# -----------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------
app = Flask(__name__)

# ⚠️  PRODUCTION: replace with your real frontend origin
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# -----------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET    = os.getenv("PLAID_SECRET")
PLAID_ENV       = os.getenv("PLAID_ENV", "sandbox")   # sandbox | development | production

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
    api_client  = ApiClient(configuration)
    plaid_client = plaid_api.PlaidApi(api_client)

# -----------------------------------------------------------------------
# A simple API-key guard.
# Set API_KEY in your .env; pass it as  Authorization: Bearer <key>
# Replace this with proper JWT auth (e.g. Flask-JWT-Extended) in production.
# -----------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            # If no API_KEY is configured, auth is disabled (dev-only convenience)
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


# -----------------------------------------------------------------------
# Persistent token storage — SQLite (upgrade to Postgres + encryption in prod)
#
# Each user gets their own row keyed by user_id.
# In a real app user_id comes from the validated JWT; here we accept it
# from the request body / header so you can demo multi-user behaviour.
# -----------------------------------------------------------------------
DB_PATH = os.getenv("SQLITE_PATH", "plaid_tokens.db")


def get_db():
    """Return a per-request SQLite connection (stored on Flask's g object)."""
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plaid_items (
                user_id     TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                item_id      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        conn.commit()


# -----------------------------------------------------------------------
# Token helpers
# -----------------------------------------------------------------------

def save_token(user_id: str, access_token: str, item_id: str):
    """Upsert an access token for user_id."""
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


def load_token(user_id: str):
    """Return (access_token, item_id) for user_id, or (None, None)."""
    row = get_db().execute(
        "SELECT access_token, item_id FROM plaid_items WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return (row["access_token"], row["item_id"]) if row else (None, None)


def delete_token(user_id: str):
    conn = get_db()
    conn.execute("DELETE FROM plaid_items WHERE user_id = ?", (user_id,))
    conn.commit()


# -----------------------------------------------------------------------
# Plaid error helper
# -----------------------------------------------------------------------

def handle_plaid_exception(e: ApiException):
    """Parse a Plaid ApiException and return a JSON response + HTTP status."""
    try:
        body = json.loads(e.body)
    except Exception:
        body = {}

    error_code    = body.get("error_code", "UNKNOWN")
    error_message = body.get("error_message", str(e))
    error_type    = body.get("error_type", "API_ERROR")

    logger.error("Plaid API error: type=%s code=%s message=%s",
                 error_type, error_code, error_message)

    # Map specific codes to meaningful HTTP statuses
    status_map = {
        "ITEM_LOGIN_REQUIRED":    401,
        "INVALID_ACCESS_TOKEN":   401,
        "INVALID_PUBLIC_TOKEN":   400,
        "RATE_LIMIT_EXCEEDED":    429,
        "INSTITUTION_DOWN":       503,
    }
    http_status = status_map.get(error_code, 502)

    return jsonify({
        "success":       False,
        "error":         error_message,
        "error_code":    error_code,
        "error_type":    error_type,
        "requires_reauth": error_code == "ITEM_LOGIN_REQUIRED",
    }), http_status


# -----------------------------------------------------------------------
# Fake data generators (simulation / sandbox fallback)
# -----------------------------------------------------------------------

def generate_fake_accounts():
    return [
        {
            "account_id": "fake_checking_001",
            "balances": {"available": 2500.50, "current": 2500.50,
                         "limit": None, "iso_currency_code": "USD"},
            "mask": "4321", "name": "Plaid Checking",
            "official_name": "Plaid Silver Standard 0.1% Interest Checking",
            "subtype": "checking", "type": "depository"
        },
        {
            "account_id": "fake_savings_001",
            "balances": {"available": 10000.00, "current": 10000.00,
                         "limit": None, "iso_currency_code": "USD"},
            "mask": "5678", "name": "Plaid Saving",
            "official_name": "Plaid Bronze Standard 0.2% Interest Saving",
            "subtype": "savings", "type": "depository"
        },
        {
            "account_id": "fake_credit_001",
            "balances": {"available": 3500.00, "current": 1500.00,
                         "limit": 5000, "iso_currency_code": "USD"},
            "mask": "9012", "name": "Plaid Credit Card",
            "official_name": "Plaid Diamond 12.5% APR Interest Credit Card",
            "subtype": "credit card", "type": "credit"
        },
    ]


def generate_fake_transactions(days=30, num_transactions=90):
    merchants_by_category = {
        "Food and Drink": [
            ("Starbucks", 4.50, 8.00), ("McDonald's", 8.00, 15.00),
            ("Chipotle", 10.00, 18.00), ("Whole Foods", 30.00, 120.00),
            ("Trader Joe's", 25.00, 80.00), ("Local Coffee Shop", 3.50, 7.00),
            ("Pizza Hut", 15.00, 35.00), ("Subway", 7.00, 12.00),
        ],
        "Transportation": [
            ("Uber", 8.00, 35.00), ("Lyft", 7.00, 30.00),
            ("Shell Gas Station", 30.00, 60.00), ("Chevron", 35.00, 65.00),
            ("Parking Meter", 2.00, 10.00), ("Public Transit", 2.50, 5.00),
        ],
        "Shopping": [
            ("Amazon", 10.00, 200.00), ("Target", 15.00, 150.00),
            ("Walmart", 20.00, 180.00), ("Best Buy", 25.00, 500.00),
            ("Nike Store", 50.00, 200.00), ("Apple Store", 20.00, 2000.00),
        ],
        "Entertainment": [
            ("Netflix", 15.99, 15.99), ("Spotify", 9.99, 9.99),
            ("AMC Theaters", 12.00, 30.00), ("Steam Games", 5.00, 60.00),
            ("PlayStation Store", 10.00, 70.00),
        ],
        "Bills & Utilities": [
            ("Electric Company", 80.00, 150.00), ("Internet Provider", 59.99, 59.99),
            ("Water Company", 30.00, 50.00), ("Phone Bill", 45.00, 85.00),
            ("Insurance", 100.00, 200.00),
        ],
        "Healthcare": [
            ("CVS Pharmacy", 10.00, 50.00), ("Walgreens", 8.00, 45.00),
            ("Doctor's Office", 25.00, 200.00), ("Dentist", 50.00, 300.00),
        ],
        "Transfer": [
            ("Venmo", 10.00, 100.00), ("PayPal", 5.00, 200.00),
            ("Zelle Payment", 20.00, 150.00),
        ],
    }

    transactions = []
    for i in range(num_transactions):
        days_ago         = random.randint(0, days)
        transaction_date = datetime.now() - timedelta(days=days_ago)
        category         = random.choice(list(merchants_by_category.keys()))
        merchant_data    = random.choice(merchants_by_category[category])
        merchant_name, min_amt, max_amt = merchant_data
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
            "personal_finance_category": {
                "primary":  category,
                "detailed": f"{category}_{merchant_name.lower().replace(' ', '_')}",
            },
            "transaction_type": "place",
        })

    return sorted(transactions, key=lambda x: x["date"], reverse=True)


# -----------------------------------------------------------------------
# AI analysis (rule-based)
# -----------------------------------------------------------------------

def analyze_transactions(transactions):
    if not transactions:
        return {"error": "No transactions to analyze",
                "suggestions": ["Connect a bank account to see insights"]}

    total_spent  = 0.0
    total_income = 0.0
    categories   = {}
    merchants    = {}
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

        categories[category] = categories.get(category, 0) + amount

        if merchant not in merchants:
            merchants[merchant] = {"count": 0, "total": 0.0}
        merchants[merchant]["count"] += 1
        merchants[merchant]["total"] += amount

        daily_spending[date] = daily_spending.get(date, 0.0) + amount

    avg_daily_spend = round(total_spent / len(daily_spending), 2) if daily_spending else 0

    top_merchants = sorted(
        [(m, d["count"], d["total"]) for m, d in merchants.items()],
        key=lambda x: x[1], reverse=True
    )[:5]

    sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)

    return {
        "summary": {
            "total_spent":       round(total_spent, 2),
            "total_income":      round(total_income, 2),
            "net_cash_flow":     round(total_income - total_spent, 2),
            "transaction_count": len(transactions),
            "avg_transaction":   round(total_spent / len(transactions), 2) if transactions else 0,
            "avg_daily_spend":   avg_daily_spend,
        },
        "categories": {
            "breakdown":            {c: round(a, 2) for c, a in sorted_categories},
            "top_category":         sorted_categories[0][0] if sorted_categories else None,
            "top_category_amount":  round(sorted_categories[0][1], 2) if sorted_categories else 0,
        },
        "merchants": {
            "most_frequent": [
                {"name": m[0], "visits": m[1], "total_spent": round(m[2], 2)}
                for m in top_merchants
            ]
        },
        "patterns": {
            "spending_trend": (
                "increasing"
                if len(transactions) > 10
                and sum(tx["amount"] for tx in transactions[:5]) >
                   sum(tx["amount"] for tx in transactions[5:10])
                else "stable"
            ),
            "biggest_expense_day": (
                max(daily_spending.items(), key=lambda x: x[1])[0]
                if daily_spending else None
            ),
        },
        "recommendations": generate_recommendations(categories, total_spent, avg_daily_spend),
    }


def generate_recommendations(categories, total_spent, avg_daily_spend):
    recommendations = []

    if total_spent == 0:
        return recommendations

    food_pct      = categories.get("Food and Drink", 0) / total_spent
    transport_pct = categories.get("Transportation", 0) / total_spent
    shopping_pct  = categories.get("Shopping", 0) / total_spent

    if food_pct > 0.30:
        recommendations.append({
            "category":  "Food & Drink",
            "insight":   f"You're spending {round(food_pct * 100, 1)}% on food",
            "suggestion": "Consider meal planning or cooking at home more often",
        })
    if transport_pct > 0.20:
        recommendations.append({
            "category":  "Transportation",
            "insight":   f"Transportation is {round(transport_pct * 100, 1)}% of spending",
            "suggestion": "Look into public transit passes or carpooling options",
        })
    if avg_daily_spend > 100:
        recommendations.append({
            "category":  "Daily Budget",
            "insight":   f"Average daily spend is ${avg_daily_spend}",
            "suggestion": "Set a daily spending limit to better control expenses",
        })
    if shopping_pct > 0.25:
        recommendations.append({
            "category":  "Shopping",
            "insight":   "Shopping represents a significant portion of your expenses",
            "suggestion": "Try the 24-hour rule before making non-essential purchases",
        })

    return recommendations


# -----------------------------------------------------------------------
# Input validation helpers
# -----------------------------------------------------------------------

def validate_days(value, default=30, min_val=1, max_val=730):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default, None
    if not (min_val <= days <= max_val):
        return None, f"'days' must be between {min_val} and {max_val}"
    return days, None


def get_user_id():
    """
    Extract user_id from request.
    Replace this with JWT sub-claim extraction in production.
    """
    return request.headers.get("X-User-Id", "default_user")


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "app":               "Flask + Plaid Transaction Simulator",
        "version":           "2.0",
        "plaid_environment": PLAID_ENV,
        "simulation_mode":   SIMULATION_MODE,
        "endpoints": [
            "POST /create_link_token  — Create Plaid Link token",
            "POST /exchange_token     — Exchange public token for access token",
            "GET  /accounts           — Get bank accounts",
            "GET  /transactions       — Get paginated transactions + AI insights",
            "POST /simulate           — Generate fake data (dev only)",
            "POST /reset              — Clear stored token (current user)",
        ],
    })


@app.route("/create_link_token", methods=["POST"])
@require_auth
def create_link_token():
    user_id = get_user_id()

    if SIMULATION_MODE:
        return jsonify({
            "success":         True,
            "link_token":      "fake-link-token-for-testing",
            "simulation_mode": True,
        })

    try:
        req = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="AI Cash Manager",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = plaid_client.link_token_create(req)
        return jsonify({"success": True, "link_token": response["link_token"]})

    except ApiException as e:
        return handle_plaid_exception(e)

    except Exception as e:
        logger.exception("Unexpected error in /create_link_token")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/exchange_token", methods=["POST"])
@require_auth
def exchange_token():
    user_id      = get_user_id()
    public_token = (request.json or {}).get("public_token")

    if not public_token:
        return jsonify({"success": False, "error": "Missing public_token"}), 400

    # Simulation path
    if SIMULATION_MODE or public_token == "fake-public-token":
        save_token(user_id, "fake-access-token", "fake-item-id")
        return jsonify({
            "success":         True,
            "message":         "Bank connected successfully (simulation mode)",
            "simulation_mode": True,
        })

    try:
        response = plaid_client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        save_token(user_id, response["access_token"], response["item_id"])
        return jsonify({"success": True, "message": "Bank connected successfully"})

    except ApiException as e:
        return handle_plaid_exception(e)

    except Exception as e:
        logger.exception("Unexpected error in /exchange_token")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/accounts", methods=["GET"])
@require_auth
def get_accounts():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    # Simulation path
    if SIMULATION_MODE or access_token == "fake-access-token":
        return jsonify({
            "success":         True,
            "accounts":        generate_fake_accounts(),
            "simulation_mode": True,
        })

    if not access_token:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    try:
        response = plaid_client.accounts_get(
            AccountsGetRequest(access_token=access_token)
        )
        # Serialize Plaid model objects to plain dicts
        accounts = [dict(a) for a in response["accounts"]]
        return jsonify({"success": True, "accounts": accounts})

    except ApiException as e:
        return handle_plaid_exception(e)

    except Exception as e:
        logger.exception("Unexpected error in /accounts")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/transactions", methods=["GET"])
@require_auth
def get_transactions():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)

    # ── Validate query params ──────────────────────────────────────────
    days, err = validate_days(request.args.get("days", 30))
    if err:
        return jsonify({"success": False, "error": err}), 400

    page_size, err = validate_days(
        request.args.get("page_size", 50), default=50, min_val=1, max_val=500
    )
    if err:
        return jsonify({"success": False, "error": err}), 400

    offset, err = validate_days(
        request.args.get("offset", 0), default=0, min_val=0, max_val=100_000
    )
    if err:
        return jsonify({"success": False, "error": err}), 400

    # ── Simulation path ────────────────────────────────────────────────
    if SIMULATION_MODE or access_token == "fake-access-token":
        all_transactions = generate_fake_transactions(days=days, num_transactions=90)
        page             = all_transactions[offset: offset + page_size]
        insights         = analyze_transactions(all_transactions)

        return jsonify({
            "success":            True,
            "transactions":       page,
            "total_transactions": len(all_transactions),
            "offset":             offset,
            "page_size":          page_size,
            "has_more":           (offset + page_size) < len(all_transactions),
            "ai_insights":        insights,
            "simulation_mode":    True,
        })

    if not access_token:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    # ── Real Plaid path with full pagination ───────────────────────────
    try:
        end_date   = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # ── Page 1 ──
        first_response = plaid_client.transactions_get(
            TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=TransactionsGetRequestOptions(
                    count=500,   # max per request
                    offset=0,
                ),
            )
        )
        all_transactions  = list(first_response["transactions"])
        total_transactions = first_response["total_transactions"]

        # ── Subsequent pages ──
        while len(all_transactions) < total_transactions:
            response = plaid_client.transactions_get(
                TransactionsGetRequest(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options=TransactionsGetRequestOptions(
                        count=500,
                        offset=len(all_transactions),
                    ),
                )
            )
            fetched = list(response["transactions"])
            if not fetched:
                # Guard against infinite loop if API behaves unexpectedly
                logger.warning(
                    "Plaid returned 0 transactions but total_transactions=%d; stopping pagination.",
                    total_transactions,
                )
                break
            all_transactions.extend(fetched)

        logger.info(
            "Fetched %d/%d transactions for user=%s days=%d",
            len(all_transactions), total_transactions, user_id, days
        )

        # Serialize Plaid model objects
        all_transactions = [dict(tx) for tx in all_transactions]

        # Serve requested page from the full in-memory set
        page     = all_transactions[offset: offset + page_size]
        insights = analyze_transactions(all_transactions)

        return jsonify({
            "success":            True,
            "transactions":       page,
            "total_transactions": total_transactions,
            "offset":             offset,
            "page_size":          page_size,
            "has_more":           (offset + page_size) < total_transactions,
            "ai_insights":        insights,
        })

    except ApiException as e:
        return handle_plaid_exception(e)

    except Exception as e:
        logger.exception("Unexpected error in /transactions")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.route("/simulate", methods=["POST"])
@require_auth
def simulate():
    """Force simulation mode — dev / testing only. Remove in production."""
    user_id = get_user_id()
    body    = request.json or {}

    days_val, err = validate_days(body.get("days", 30))
    if err:
        return jsonify({"success": False, "error": err}), 400

    num_tx_val, err = validate_days(
        body.get("num_transactions", 90), default=90, min_val=1, max_val=500
    )
    if err:
        return jsonify({"success": False, "error": err}), 400

    save_token(user_id, "fake-access-token", "fake-item-id")
    fake_tx = generate_fake_transactions(days=days_val, num_transactions=num_tx_val)

    return jsonify({
        "success": True,
        "message": "Simulation data generated",
        "stats": {
            "accounts":     len(generate_fake_accounts()),
            "transactions": len(fake_tx),
        },
    })


@app.route("/reset", methods=["POST"])
@require_auth
def reset():
    """Disconnect the current user's bank link."""
    user_id = get_user_id()
    delete_token(user_id)
    return jsonify({"success": True, "message": f"Token cleared for user {user_id}"})


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
    print("  AI CASH MANAGER — Flask + Plaid Backend  v2.0")
    print("=" * 60)
    print(f"  Plaid environment : {PLAID_ENV}")
    print(f"  Simulation mode   : {SIMULATION_MODE}")
    print(f"  Allowed origins   : {ALLOWED_ORIGINS}")
    print(f"  Token storage     : {DB_PATH}")
    print(f"  Auth              : {'API_KEY set' if API_KEY else 'DISABLED (set API_KEY in .env)'}")
    print("=" * 60)

    # Never run debug=True in production — use gunicorn/uvicorn instead
    app.run(debug=(PLAID_ENV == "sandbox"), port=5000)
