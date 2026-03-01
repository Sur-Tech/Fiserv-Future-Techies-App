import hmac
import json
import logging
import os
import random
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from groq import Groq
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.exceptions import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cashlens")

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT  = int(os.getenv("GROQ_TIMEOUT", "30"))

groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq AI ready (model=%s).", GROQ_MODEL)
else:
    logger.warning("GROQ_API_KEY not set -- AI features disabled.")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8080,https://fiserv-future-techies-app-glhq.vercel.app"
).split(",")]
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "").strip()
PLAID_SECRET    = os.getenv("PLAID_SECRET", "").strip()
PLAID_ENV       = os.getenv("PLAID_ENV", "sandbox").strip().lower()

PLAID_HOSTS = {
    "sandbox":     "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production":  "https://production.plaid.com",
}

if PLAID_ENV not in PLAID_HOSTS:
    raise ValueError(f"Invalid PLAID_ENV={PLAID_ENV!r}. Must be one of: {list(PLAID_HOSTS.keys())}")

SIMULATION_MODE = not (PLAID_CLIENT_ID and PLAID_SECRET)

plaid_client = None
if not SIMULATION_MODE:
    _cfg = Configuration(
        host=PLAID_HOSTS[PLAID_ENV],
        api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
    )
    plaid_client = plaid_api.PlaidApi(ApiClient(_cfg))
    logger.info("Plaid client ready (env=%s).", PLAID_ENV)
else:
    logger.warning("Plaid credentials missing -- SIMULATION MODE active.")

API_KEY = os.getenv("API_KEY", "").strip()
_MAX_USER_ID_LEN      = 128
_MAX_CATEGORY_LEN     = 100
_MAX_CHAT_MESSAGE_LEN = 1000


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            logger.warning("API_KEY not configured -- auth DISABLED")
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error(401, "Missing or malformed Authorization header")
        token = auth_header[7:].strip()
        if not hmac.compare_digest(token.encode("utf-8"), API_KEY.encode("utf-8")):
            logger.warning("Invalid API key attempt from %s", request.remote_addr)
            return _error(401, "Invalid API key")
        return f(*args, **kwargs)
    return decorated


def get_user_id():
    raw     = request.headers.get("X-User-Id", "default_user")
    user_id = re.sub(r"[^\w\-@.]", "", raw.strip())[:_MAX_USER_ID_LEN]
    return user_id or "default_user"


def _error(status, message, **extra):
    return jsonify({"success": False, "data": None, "error": message, **extra}), status


def _ok(**data):
    return jsonify({"success": True, "data": data, "error": None})


@app.before_request
def _attach_request_id():
    g.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())[:8]
    g.start_time = time.monotonic()


@app.after_request
def _log_and_tag(response):
    ms = (time.monotonic() - getattr(g, "start_time", time.monotonic())) * 1000
    logger.info("[%s] %s %s -> %d (%.1f ms)",
                getattr(g, "request_id", "-"), request.method, request.path,
                response.status_code, ms)
    response.headers["X-Request-Id"] = getattr(g, "request_id", "-")
    return response


DB_PATH = os.getenv("SQLITE_PATH", "/tmp/domus.db" if os.getenv("VERCEL") else "cashlens.db")


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        conn = get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS plaid_items (
                user_id      TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                item_id      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                report_type  TEXT NOT NULL,
                report_text  TEXT NOT NULL,
                stats_json   TEXT NOT NULL,
                created_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reports_user_date
                ON ai_reports(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS user_budgets (
                user_id       TEXT NOT NULL,
                category      TEXT NOT NULL,
                monthly_limit REAL NOT NULL CHECK(monthly_limit >= 0),
                set_by        TEXT NOT NULL DEFAULT 'ai' CHECK(set_by IN ('ai','user')),
                updated_at    TEXT NOT NULL,
                PRIMARY KEY (user_id, category)
            );
            CREATE INDEX IF NOT EXISTS idx_budgets_user ON user_budgets(user_id);
        """)
        logger.info("Database initialised at %s.", DB_PATH)


init_db()


def save_token(user_id, access_token, item_id):
    now  = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO plaid_items (user_id, access_token, item_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                item_id      = excluded.item_id,
                updated_at   = excluded.updated_at
        """, (user_id, access_token, item_id, now, now))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("save_token failed user=%s: %s", user_id, e)
        raise


def load_token(user_id):
    row = get_db().execute(
        "SELECT access_token, item_id FROM plaid_items WHERE user_id = ?", (user_id,)
    ).fetchone()
    return (row["access_token"], row["item_id"]) if row else (None, None)


def delete_token(user_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM plaid_items WHERE user_id = ?", (user_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("delete_token failed user=%s: %s", user_id, e)
        raise


def save_budget(user_id, category, monthly_limit, set_by="ai"):
    if set_by not in ("ai", "user"):
        raise ValueError(f"set_by must be 'ai' or 'user', got {set_by!r}")
    if monthly_limit < 0:
        raise ValueError("monthly_limit must be >= 0")
    now  = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO user_budgets (user_id, category, monthly_limit, set_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, category) DO UPDATE SET
                monthly_limit = excluded.monthly_limit,
                set_by        = excluded.set_by,
                updated_at    = excluded.updated_at
        """, (user_id, category, monthly_limit, set_by, now))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("save_budget failed user=%s cat=%s: %s", user_id, category, e)
        raise


def load_budgets(user_id):
    rows = get_db().execute(
        "SELECT category, monthly_limit, set_by FROM user_budgets WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {row["category"]: {"limit": row["monthly_limit"], "set_by": row["set_by"]} for row in rows}


def save_report(user_id, report_type, report_text, stats):
    now  = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO ai_reports (user_id, report_type, report_text, stats_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, report_type, report_text, json.dumps(stats), now))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("save_report failed user=%s: %s", user_id, e)
        raise


def load_report_history(user_id, limit=5):
    rows = get_db().execute("""
        SELECT id, report_type, report_text, stats_json, created_at
        FROM ai_reports WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    result = []
    for row in rows:
        try:
            stats = json.loads(row["stats_json"])
        except (json.JSONDecodeError, TypeError):
            stats = {}
        result.append({"id": row["id"], "type": row["report_type"],
                        "report": row["report_text"], "stats": stats,
                        "created_at": row["created_at"]})
    return result


_PLAID_STATUS_MAP = {
    "ITEM_LOGIN_REQUIRED": 401, "INVALID_ACCESS_TOKEN": 401,
    "INVALID_PUBLIC_TOKEN": 400, "INSUFFICIENT_CREDENTIALS": 400,
    "RATE_LIMIT_EXCEEDED": 429, "INSTITUTION_DOWN": 503,
}


def handle_plaid_exception(e):
    try:
        body = json.loads(e.body) if isinstance(e.body, (str, bytes)) else {}
    except (json.JSONDecodeError, AttributeError):
        body = {}
    error_code    = str(body.get("error_code",    "UNKNOWN"))
    error_message = str(body.get("error_message", "Plaid API error"))
    error_type    = str(body.get("error_type",    "API_ERROR"))
    logger.error("Plaid error: type=%s code=%s msg=%s", error_type, error_code, error_message)
    return _error(_PLAID_STATUS_MAP.get(error_code, 502), error_message,
                  error_code=error_code, error_type=error_type,
                  requires_reauth=(error_code == "ITEM_LOGIN_REQUIRED"))


def validate_int_param(value, default, min_val, max_val):
    if value is None or value == "":
        return default, None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None, f"Invalid value {value!r} -- must be an integer"
    if not (min_val <= v <= max_val):
        return None, f"Value {v} out of range [{min_val}, {max_val}]"
    return v, None


def sanitize_text(text, max_len):
    return str(text).replace("\x00", "").strip()[:max_len]


def guard_prompt_injection(text):
    lowered = text.lower()
    for pat in ["ignore previous","ignore all","disregard","forget instructions",
                "new instructions","override","system prompt","act as","you are now",
                "jailbreak","dan mode","developer mode"]:
        if pat in lowered:
            logger.warning("[%s] Prompt injection blocked: %r",
                           getattr(g, "request_id", "-"), text[:120])
            return "[Message blocked by security filter]"
    return text


_MERCHANTS = {
    "Food and Drink":    [("Starbucks",4.5,8),("McDonald's",8,15),("Chipotle",10,18),
                          ("Whole Foods",30,120),("Trader Joe's",25,80),("Pizza Hut",15,35),("Subway",7,12)],
    "Transportation":    [("Uber",8,35),("Lyft",7,30),("Shell Gas Station",30,60),
                          ("Chevron",35,65),("Parking Meter",2,10),("Public Transit",2.5,5)],
    "Shopping":          [("Amazon",10,200),("Target",15,150),("Walmart",20,180),
                          ("Best Buy",25,500),("Nike Store",50,200),("Apple Store",20,2000)],
    "Entertainment":     [("Netflix",15.99,15.99),("Spotify",9.99,9.99),("AMC Theaters",12,30),
                          ("Steam Games",5,60),("PlayStation Store",10,70)],
    "Bills & Utilities": [("Electric Company",80,150),("Internet Provider",59.99,59.99),
                          ("Water Company",30,50),("Phone Bill",45,85),("Insurance",100,200)],
    "Healthcare":        [("CVS Pharmacy",10,50),("Walgreens",8,45),
                          ("Doctor's Office",25,200),("Dentist",50,300)],
    "Transfer":          [("Venmo",10,100),("PayPal",5,200),("Zelle Payment",20,150)],
}


def generate_fake_accounts():
    return [
        {"account_id":"fake_checking_001","balances":{"available":2500.50,"current":2500.50,"limit":None,"iso_currency_code":"USD"},
         "mask":"4321","name":"Plaid Checking","official_name":"Plaid Silver Standard 0.1% Interest Checking","subtype":"checking","type":"depository"},
        {"account_id":"fake_savings_001","balances":{"available":10000.00,"current":10000.00,"limit":None,"iso_currency_code":"USD"},
         "mask":"5678","name":"Plaid Saving","official_name":"Plaid Bronze Standard 0.2% Interest Saving","subtype":"savings","type":"depository"},
        {"account_id":"fake_credit_001","balances":{"available":3500.00,"current":1500.00,"limit":5000,"iso_currency_code":"USD"},
         "mask":"9012","name":"Plaid Credit Card","official_name":"Plaid Diamond 12.5% APR Interest Credit Card","subtype":"credit card","type":"credit"},
    ]


def generate_fake_transactions(days=30, num_transactions=90):
    txs = []
    for i in range(num_transactions):
        days_ago     = random.randint(0, days)
        tx_date      = datetime.now(timezone.utc) - timedelta(days=days_ago)
        category     = random.choice(list(_MERCHANTS.keys()))
        name, lo, hi = random.choice(_MERCHANTS[category])
        txs.append({
            "transaction_id": f"fake_tx_{i:04d}",
            "account_id":     random.choice(["fake_checking_001","fake_credit_001"]),
            "amount":         round(random.uniform(lo, hi), 2),
            "iso_currency_code": "USD", "category": [category],
            "date":           tx_date.strftime("%Y-%m-%d"),
            "authorized_date":tx_date.strftime("%Y-%m-%d"),
            "name":           name.upper(), "merchant_name": name,
            "payment_channel":random.choice(["in store","online","other"]),
            "pending":        days_ago <= 2 and random.random() < 0.3,
            "transaction_type":"place",
        })
    return sorted(txs, key=lambda x: x["date"], reverse=True)


def calculate_stats(transactions):
    if not transactions:
        return None
    total_spent = total_income = 0.0
    categories = {}
    merchants  = {}
    daily_spending = {}
    for tx in transactions:
        try:
            amount   = float(tx.get("amount", 0))
            date     = str(tx.get("date", ""))
            merchant = str(tx.get("merchant_name") or tx.get("name") or "Unknown")
        except (TypeError, ValueError):
            continue
        if amount > 0:
            total_spent += amount
        else:
            total_income += abs(amount)
        raw_cat  = tx.get("category")
        # Plaid v2 API uses personal_finance_category.primary instead of legacy category
        pfc = tx.get("personal_finance_category")
        if pfc and isinstance(pfc, dict) and pfc.get("primary"):
            category = pfc["primary"].replace("_", " ").title()
        elif isinstance(raw_cat, list) and raw_cat:
            category = raw_cat[0]
        elif raw_cat:
            category = str(raw_cat)
        else:
            category = "Other"
        categories[category] = categories.get(category, 0.0) + amount
        if merchant not in merchants:
            merchants[merchant] = {"count": 0, "total": 0.0}
        merchants[merchant]["count"] += 1
        merchants[merchant]["total"] += amount
        if date:
            daily_spending[date] = daily_spending.get(date, 0.0) + amount
    n_days      = max(len(daily_spending), 1)
    n_tx        = max(len(transactions), 1)
    sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    top_merch   = sorted([(m,d["count"],d["total"]) for m,d in merchants.items()],
                          key=lambda x: x[1], reverse=True)[:5]
    return {
        "total_spent":         round(total_spent, 2),
        "total_income":        round(total_income, 2),
        "net_cash_flow":       round(total_income - total_spent, 2),
        "transaction_count":   len(transactions),
        "avg_daily_spend":     round(total_spent / n_days, 2),
        "avg_transaction":     round(total_spent / n_tx, 2),
        "category_breakdown":  {c: round(a, 2) for c, a in sorted_cats},
        "top_category":        sorted_cats[0][0] if sorted_cats else None,
        "top_category_amount": round(sorted_cats[0][1], 2) if sorted_cats else 0.0,
        "top_merchants":       [{"name":m[0],"visits":m[1],"total":round(m[2],2)} for m in top_merch],
        "biggest_expense_day": max(daily_spending, key=daily_spending.get) if daily_spending else None,
    }


def detect_recurring_transactions(transactions):
    """Group by merchant; flag those that appear across 2+ calendar months."""
    from collections import defaultdict
    merchant_txs = defaultdict(list)
    for tx in transactions:
        name = (tx.get("merchant_name") or tx.get("name") or "").strip()
        # Normalise: lowercase, strip trailing digits/symbols (e.g. "AMAZON #1234" → "amazon")
        key = re.sub(r'[\s\d#*]+$', '', name.lower()).strip()
        if key:
            merchant_txs[key].append(tx)

    recurring = []
    for key, txs in merchant_txs.items():
        if len(txs) < 2:
            continue
        months = set()
        for tx in txs:
            date_str = str(tx.get("date", ""))
            if len(date_str) >= 7:
                months.add(date_str[:7])
        if len(months) < 2:
            continue
        amounts = [float(tx.get("amount", 0)) for tx in txs if float(tx.get("amount", 0)) > 0]
        if not amounts:
            continue
        avg_amount = sum(amounts) / len(amounts)
        raw_cat = txs[0].get("category")
        pfc0 = txs[0].get("personal_finance_category")
        if pfc0 and isinstance(pfc0, dict) and pfc0.get("primary"):
            category = pfc0["primary"].replace("_", " ").title()
        elif isinstance(raw_cat, list) and raw_cat:
            category = raw_cat[0]
        else:
            category = str(raw_cat) if raw_cat else "Other"
        amount_variance = max(abs(a - avg_amount) for a in amounts) / avg_amount if avg_amount else 1
        recurring.append({
            "merchant":        txs[0].get("merchant_name") or txs[0].get("name") or key,
            "count":           len(txs),
            "months_seen":     sorted(months),
            "avg_amount":      round(avg_amount, 2),
            "total":           round(sum(amounts), 2),
            "category":        category,
            "is_subscription": amount_variance < 0.05,  # same amount every time = subscription
        })

    recurring.sort(key=lambda x: x["total"], reverse=True)
    return recurring


def detect_anomalies(transactions, threshold=2.0):
    """Flag transactions where amount > threshold × category average."""
    from collections import defaultdict
    cat_groups = defaultdict(list)
    for tx in transactions:
        amount = float(tx.get("amount", 0))
        if amount <= 0:
            continue
        raw_cat = tx.get("category")
        pfc = tx.get("personal_finance_category")
        if pfc and isinstance(pfc, dict) and pfc.get("primary"):
            cat = pfc["primary"].replace("_", " ").title()
        elif isinstance(raw_cat, list) and raw_cat:
            cat = raw_cat[0]
        else:
            cat = str(raw_cat) if raw_cat else "Other"
        cat_groups[cat].append((amount, tx))

    anomalies = []
    for cat, items in cat_groups.items():
        avg = sum(a for a, _ in items) / len(items)
        if avg <= 0:
            continue
        for amount, tx in items:
            if amount > threshold * avg:
                anomalies.append({
                    "transaction_id": tx.get("transaction_id"),
                    "merchant":       tx.get("merchant_name") or tx.get("name") or "Unknown",
                    "amount":         round(amount, 2),
                    "category":       cat,
                    "date":           tx.get("date"),
                    "category_avg":   round(avg, 2),
                    "ratio":          round(amount / avg, 1),
                    "flag":           f"${amount:.2f} is {round(amount/avg,1)}x the ${avg:.2f} average for {cat}",
                })

    anomalies.sort(key=lambda x: x["ratio"], reverse=True)
    return anomalies


def groq_generate(prompt):
    if not groq_client:
        return "AI unavailable -- set GROQ_API_KEY in your .env file."
    try:
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("Groq error: %s", e)
        return "AI temporarily unavailable. Please try again."


def _fmt_categories(stats):
    return "\n".join(f"  - {c}: ${a:.2f}" for c, a in stats["category_breakdown"].items())

def _fmt_merchants(stats):
    return "\n".join(f"  - {m['name']}: {m['visits']} visits, ${m['total']:.2f} total"
                     for m in stats["top_merchants"])

def _fmt_budgets(budgets):
    if not budgets:
        return "  No budgets set yet."
    return "\n".join(f"  - {cat}: ${info['limit']:.2f}/month (set by {info['set_by']})"
                     for cat, info in budgets.items())

def _tx_category(tx):
    """Extract category string from a single transaction dict."""
    pfc = tx.get("personal_finance_category")
    if pfc and isinstance(pfc, dict) and pfc.get("primary"):
        return pfc["primary"].replace("_", " ").title()
    raw = tx.get("category")
    if isinstance(raw, list) and raw:
        return raw[0]
    return str(raw) if raw else "Other"


def groq_spending_report(stats, budgets, period_days):
    prompt = f"""You are Domus, a personal financial advisor writing a report directly to the user.
Be warm, direct, and specific. Use actual dollar amounts from their data.
Do NOT give generic advice -- reference THEIR specific spending habits.
Use clear sections with emoji headers. Keep it under 400 words.

THEIR SPENDING DATA -- last {period_days} days:
SUMMARY:
  - Total spent: ${stats['total_spent']:.2f}
  - Total income recorded: ${stats['total_income']:.2f}
  - Net cash flow: ${stats['net_cash_flow']:.2f}
  - Number of transactions: {stats['transaction_count']}
  - Average daily spend: ${stats['avg_daily_spend']:.2f}
  - Biggest spending day: {stats['biggest_expense_day']}
SPENDING BY CATEGORY:\n{_fmt_categories(stats)}
TOP MERCHANTS VISITED:\n{_fmt_merchants(stats)}
CURRENT BUDGETS:\n{_fmt_budgets(budgets)}
Write a report that:
1. Opens with a one-line verdict on their financial health
2. Names exactly what they spent the most on and whether that is a concern
3. Calls out any categories where they blew their budget
4. Gives 3 specific, actionable things they should do THIS WEEK
5. Ends with a short encouraging note"""
    return groq_generate(prompt)


def groq_budget_recommendations(stats):
    prompt = f"""You are a personal AI financial advisor.
Based on this user's real spending, recommend sensible monthly budgets for each category.
Their spending:\n{_fmt_categories(stats)}
Average daily spend: ${stats['avg_daily_spend']:.2f}
Net cash flow: ${stats['net_cash_flow']:.2f}
Rules:
- If net cash flow is negative (overspending), cut budgets 10-20% below current spend
- If net cash flow is positive (saving), set budgets close to current spend
- Only include categories from the data above
- Never cut any budget by more than 30% at once
- All values must be positive numbers
Respond ONLY with valid JSON -- no explanation, no markdown, no code fences.
Example: {{"Food and Drink": 400, "Transportation": 150}}"""
    raw   = groq_generate(prompt)
    clean = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
    match = re.search(r"\{[^{}]+\}", clean, re.DOTALL)
    if not match:
        logger.warning("Groq budget response had no JSON: %r", raw[:200])
        return {}
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError as e:
        logger.warning("Groq budget parse error: %s | raw=%r", e, raw[:200])
        return {}
    result = {}
    for cat, val in parsed.items():
        cat_clean = sanitize_text(str(cat), _MAX_CATEGORY_LEN)
        try:
            f_val = float(val)
        except (TypeError, ValueError):
            logger.warning("Non-numeric Groq budget '%s': %r", cat, val)
            continue
        if f_val < 0 or f_val > 100_000:
            logger.warning("Out-of-range Groq budget '%s': %s", cat, f_val)
            continue
        result[cat_clean] = round(f_val, 2)
    return result


def groq_alert(stats, budgets):
    over_budget = [
        {"category": cat, "spent": round(spent, 2),
         "limit": round(budgets[cat]["limit"], 2),
         "over_by": round(spent - budgets[cat]["limit"], 2)}
        for cat, spent in stats["category_breakdown"].items()
        if cat in budgets and spent > budgets[cat]["limit"]
    ]
    if not over_budget and stats["net_cash_flow"] >= 0:
        return "All budgets on track! You're managing your money well this period."
    over_text = "\n".join(
        f"  - {o['category']}: spent ${o['spent']:.2f} vs limit ${o['limit']:.2f} (over by ${o['over_by']:.2f})"
        for o in over_budget
    ) or "  No individual category overages."
    cash_note = "NEGATIVE -- spending more than income recorded!" if stats["net_cash_flow"] < 0 else "positive"
    prompt = f"""You are Domus sending an urgent but caring spending alert to a user.
Be specific, direct, and helpful. Under 150 words. Use emoji.
OVERSPENT CATEGORIES:\n{over_text}
NET CASH FLOW: ${stats['net_cash_flow']:.2f} ({cash_note})
Write a short alert that:
1. Directly names which categories they overspent in and by how much
2. If overall cash flow is negative, flag that clearly
3. Gives one concrete action they can take TODAY to fix it"""
    return groq_generate(prompt)


def _rule_based_chat(message, stats, budgets):  # noqa: C901
    """Smart conversational AI using real transaction data."""
    msg       = message.lower()
    spent     = stats.get("total_spent", 0)
    income    = stats.get("total_income", 0)
    avg       = stats.get("avg_daily_spend", 0)
    avg_tx    = stats.get("avg_transaction", 0)
    top_cat   = stats.get("top_category", "Other")
    top_amt   = stats.get("top_category_amount", 0)
    net       = stats.get("net_cash_flow", 0)
    tx_count  = stats.get("transaction_count", 0)
    cats      = stats.get("category_breakdown", {})
    merchants = stats.get("top_merchants", [])
    big_day   = stats.get("biggest_expense_day", None)

    # ── Greetings ─────────────────────────────────────────────────────────
    if any(w in msg for w in ["hello", "hi ", "hey", "howdy", "good morning", "good afternoon"]):
        return (
            f"Hey there! I'm Domus, your personal financial advisor. 👋\n\n"
            f"Here's a quick snapshot of your last 30 days:\n"
            f"• Spent: **${spent:,.2f}** across {tx_count} transactions\n"
            f"• Daily average: **${avg:.2f}/day**\n"
            f"• Cash flow: **{'✅ positive' if net >= 0 else '⚠️ negative'}** (${net:,.2f})\n\n"
            f"Ask me anything — try 'where am I spending the most?' or 'give me savings tips'!"
        )

    # ── Jokes / off-topic ─────────────────────────────────────────────────
    if any(w in msg for w in ["joke", "funny", "laugh", "humor"]):
        return (
            f"Ha! Here's a finance joke: Why did the dollar bill break up with the coin? "
            f"Because it had too many \"cents\" of humor! 😄\n\n"
            f"On a serious note, your spending this month was **${spent:,.2f}** — "
            f"not a joke, but hopefully not scary either! Want a real financial tip instead?"
        )

    # ── Summary / overview / how am I doing ───────────────────────────────
    if any(w in msg for w in ["summary", "overview", "how am i", "doing", "overall", "report"]):
        top3 = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join(f"{c} (${a:,.2f})" for c, a in top3)
        health = "great" if net > 500 else ("okay" if net >= 0 else "tight")
        return (
            f"Here's your 30-day financial overview:\n\n"
            f"💰 **Total Spent:** ${spent:,.2f}\n"
            f"📥 **Income Recorded:** ${income:,.2f}\n"
            f"{'✅' if net >= 0 else '⚠️'} **Net Cash Flow:** ${net:,.2f}\n"
            f"📊 **Daily Average:** ${avg:.2f}/day\n"
            f"🔢 **Transactions:** {tx_count} (avg ${avg_tx:.2f} each)\n\n"
            f"**Top Categories:** {top3_str}\n\n"
            f"Overall your finances look **{health}** this period. "
            + ("Keep it up! 🎉" if net >= 0 else "Consider reviewing your top spending categories to cut back.")
        )

    # ── Total spent ───────────────────────────────────────────────────────
    if any(w in msg for w in ["total", "spent", "how much", "spend this", "cost me"]):
        return (
            f"Over the last 30 days you've spent **${spent:,.2f}** across **{tx_count} transactions**, "
            f"averaging **${avg:.2f}/day** or **${avg_tx:.2f}** per purchase.\n\n"
            f"Your biggest spending area is **{top_cat}** at ${top_amt:,.2f}."
            + (f"\n\nYour biggest single-day spending was on **{big_day}**." if big_day else "")
        )

    # ── Category breakdown ────────────────────────────────────────────────
    if any(w in msg for w in ["categor", "breakdown", "where", "most", "top spend", "areas"]):
        top5 = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
        lines = "\n".join(f"  {i+1}. **{c}** — ${a:,.2f} ({a/spent*100:.0f}% of total)" for i, (c, a) in enumerate(top5) if spent > 0)
        return (
            f"Here's where your money went this month:\n\n{lines}\n\n"
            f"**{top_cat}** is your biggest category, taking up "
            f"**{top_amt/spent*100:.0f}%** of your total spending."
            if spent > 0 else
            f"Your top spending categories:\n\n" + "\n".join(f"  {i+1}. {c}: ${a:,.2f}" for i, (c, a) in enumerate(top5))
        )

    # ── Specific category lookup ──────────────────────────────────────────
    for cat_name, cat_amt in cats.items():
        if cat_name.lower() in msg or cat_name.lower().split()[0] in msg:
            pct = cat_amt / spent * 100 if spent > 0 else 0
            return (
                f"You spent **${cat_amt:,.2f}** on **{cat_name}** this month, "
                f"which is **{pct:.0f}%** of your total spending (${spent:,.2f}).\n\n"
                f"That works out to about **${cat_amt/30:.2f}/day** for this category."
            )

    # ── Merchants / stores ────────────────────────────────────────────────
    if any(w in msg for w in ["merchant", "store", "shop", "vendor", "where do i", "places"]):
        if merchants:
            lines = "\n".join(f"  {i+1}. **{m['name']}** — {m['visits']} visits, ${m['total']:,.2f} total" for i, m in enumerate(merchants[:5]))
            return f"Your most visited merchants this month:\n\n{lines}\n\nYou spend the most frequently at **{merchants[0]['name']}**."
        return "Merchant data isn't available yet — try syncing your transactions first."

    # ── Income ────────────────────────────────────────────────────────────
    if any(w in msg for w in ["income", "earn", "salary", "paycheck", "deposit"]):
        return (
            f"Income recorded in the last 30 days: **${income:,.2f}**.\n\n"
            f"After your spending of ${spent:,.2f}, your **net cash flow is ${net:,.2f}**.\n\n"
            + ("You're saving money — great work! 🎉" if net > 0 else
               "Your spending currently exceeds your recorded income. Consider tracking all income sources.")
        )

    # ── Budget ────────────────────────────────────────────────────────────
    if any(w in msg for w in ["budget", "limit", "over budget", "under budget"]):
        if budgets:
            lines = []
            for cat, info in budgets.items():
                actual = cats.get(cat, 0)
                limit  = info.get("limit", 0)
                status = "⚠️ over" if actual > limit else "✅ under"
                lines.append(f"  • **{cat}**: ${actual:,.2f} / ${limit:,.2f} limit ({status})")
            over_cats = [c for c, i in budgets.items() if cats.get(c, 0) > i["limit"]]
            return (
                f"Budget status this month:\n\n" + "\n".join(lines) +
                (f"\n\n⚠️ You're over budget in: {', '.join(over_cats)}." if over_cats else "\n\n✅ You're within all your budgets!")
            )
        return "No budgets set yet. You can set budgets in the Spending Analyzer under 'Budget Tracker'."

    # ── Savings tips / advice ─────────────────────────────────────────────
    if any(w in msg for w in ["save", "saving", "tip", "advice", "recommend", "cut", "reduce", "improve", "help me"]):
        over = [f"**{cat}** (${cats.get(cat,0) - info['limit']:,.2f} over)" for cat, info in budgets.items() if cats.get(cat, 0) > info["limit"]]
        tips = [
            f"1. **Attack your top category first** — {top_cat} at ${top_amt:,.2f} is 30%+ of budget. Look for one recurring charge to cancel.",
            f"2. **Daily spend target** — You average ${avg:.2f}/day. Setting a daily budget of ${avg*0.85:.2f} would save you **${avg*0.15*30:.0f}/month**.",
            f"3. **Automate savings** — Transfer a fixed amount on payday before you can spend it. Even $50/paycheck adds up.",
            f"4. **Review subscriptions** — Check the Recurring Transactions tab in the Spending Analyzer for forgotten subscriptions.",
        ]
        if over:
            tips.append(f"5. **Budget alert** — You're over limit on: {', '.join(over)}. Focus on these areas first.")
        return "Here are personalized savings tips based on your data:\n\n" + "\n".join(tips)

    # ── Recurring / subscriptions ─────────────────────────────────────────
    if any(w in msg for w in ["subscript", "recurring", "auto", "repeat", "netflix", "spotify", "monthly bill"]):
        return (
            "Great question! The **Recurring Transactions** section in the Spending Analyzer "
            "automatically detects merchants that charge you consistently each month.\n\n"
            "Common subscriptions to review: streaming services, gym memberships, software tools, "
            "and insurance premiums. Even canceling one $15/month subscription saves **$180/year**."
        )

    # ── Daily average ─────────────────────────────────────────────────────
    if any(w in msg for w in ["daily", "average", "per day", "day"]):
        return (
            f"Your average daily spending is **${avg:.2f}/day** over the last 30 days.\n\n"
            f"📅 Weekly: ~${avg*7:,.2f}\n"
            f"📆 Monthly: ~${avg*30:,.2f}\n"
            f"📅 Yearly projection: ~${avg*365:,.2f}\n\n"
            f"Your biggest single-day was **{big_day}**." if big_day else
            f"Your average daily spending is **${avg:.2f}/day**."
        )

    # ── Transaction count ─────────────────────────────────────────────────
    if any(w in msg for w in ["transaction", "how many", "count", "number of"]):
        return (
            f"You have **{tx_count} transactions** in the last 30 days — that's about "
            f"**{tx_count//30 or 1}–{max(tx_count//20, 2)} per day**.\n\n"
            f"Average spend per transaction: **${avg_tx:.2f}**.\n"
            f"Total spent: **${spent:,.2f}**."
        )

    # ── Net cash flow / balance ───────────────────────────────────────────
    if any(w in msg for w in ["cash flow", "net", "balance", "profit", "surplus", "deficit"]):
        return (
            f"Your 30-day net cash flow is **${net:,.2f}**.\n\n"
            f"• Income recorded: ${income:,.2f}\n"
            f"• Total spent: ${spent:,.2f}\n"
            f"• **Net: ${net:,.2f}** ({'surplus ✅' if net >= 0 else 'deficit ⚠️'})\n\n"
            + ("You're spending less than you earn — excellent financial health!" if net > 0
               else "Your spending exceeds your recorded income. Check if all income sources are linked.")
        )

    # ── Anomalies / unusual / big ─────────────────────────────────────────
    if any(w in msg for w in ["unusual", "anomal", "big purchase", "large", "weird", "strange", "spike"]):
        return (
            f"For unusual spending patterns, check the **Spending Alerts** section in the Spending Analyzer — "
            f"it flags transactions that are significantly above your average for each category.\n\n"
            f"Your average transaction is **${avg_tx:.2f}**. Anything above "
            f"**${avg_tx*2:.0f}** is worth reviewing."
        )

    # ── Comparison / trend ────────────────────────────────────────────────
    if any(w in msg for w in ["trend", "compar", "last month", "previous", "improve", "better", "worse"]):
        return (
            f"This month you spent **${spent:,.2f}** across {tx_count} transactions.\n\n"
            f"To compare with previous months, check the **Monthly Chart** in the Spending Analyzer — "
            f"it shows your spending trend over time so you can see if you're improving.\n\n"
            f"💡 Tip: A good target is to reduce monthly spending by 5–10% each month."
        )

    # ── Biggest expense day ───────────────────────────────────────────────
    if any(w in msg for w in ["biggest", "most expensive", "highest", "worst day", "max"]):
        if big_day:
            return (
                f"Your biggest spending day in the last 30 days was **{big_day}**.\n\n"
                f"Check the Spending Analyzer for a day-by-day breakdown. "
                f"Your overall biggest category is **{top_cat}** at ${top_amt:,.2f}."
            )

    # ── Generic thoughtful fallback ───────────────────────────────────────
    pct_top = top_amt / spent * 100 if spent > 0 else 0
    return (
        f"Based on your last 30 days of transactions:\n\n"
        f"💰 You've spent **${spent:,.2f}** across {tx_count} transactions\n"
        f"📊 Daily average: **${avg:.2f}/day**\n"
        f"📈 Biggest category: **{top_cat}** (${top_amt:,.2f}, {pct_top:.0f}% of total)\n"
        f"{'✅' if net >= 0 else '⚠️'} Net cash flow: **${net:,.2f}**\n\n"
        f"Some things I can help with:\n"
        f"• \"Where am I spending the most?\"\n"
        f"• \"Give me savings tips\"\n"
        f"• \"What's my daily average?\"\n"
        f"• \"Am I over budget?\"\n"
        f"• \"Show me my top merchants\""
    )


def groq_chat(user_message, stats, budgets, all_tx=None):
    safe_msg = guard_prompt_injection(sanitize_text(user_message, _MAX_CHAT_MESSAGE_LEN))
    if not groq_client:
        return _rule_based_chat(safe_msg, stats, budgets)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Recent 10 transactions
    recent_ctx = ""
    recurring_ctx = ""
    if all_tx:
        recent = sorted(
            [tx for tx in all_tx if float(tx.get("amount", 0) or 0) > 0],
            key=lambda x: str(x.get("date", "")), reverse=True
        )[:10]
        lines = [
            f"  {tx.get('date','')} | {tx.get('merchant_name') or tx.get('name','?')} | ${float(tx.get('amount',0)):.2f} | {_tx_category(tx)}"
            for tx in recent
        ]
        recent_ctx = "RECENT TRANSACTIONS (newest first):\n" + "\n".join(lines)

        recurring = detect_recurring_transactions(all_tx)
        if recurring:
            rec_lines = [
                f"  {r['merchant']}: ~${r['avg_amount']:.2f} ({'subscription' if r['is_subscription'] else 'recurring'}, {r['category']})"
                for r in recurring[:6]
            ]
            recurring_ctx = "RECURRING / SUBSCRIPTIONS:\n" + "\n".join(rec_lines)

    prompt = f"""You are Domus, a friendly personal AI financial advisor.
Answer the user's question using ONLY their real spending data below. Be conversational, specific, and concise (under 200 words).
Today's date: {today_str}

── SPENDING SUMMARY (last 30 days) ──
- Total spent:       ${stats['total_spent']:.2f}
- Income recorded:   ${stats.get('total_income', 0):.2f}
- Net cash flow:     ${stats['net_cash_flow']:.2f}
- Daily average:     ${stats['avg_daily_spend']:.2f}/day
- Avg per purchase:  ${stats.get('avg_transaction', 0):.2f}
- Transactions:      {stats['transaction_count']}
- Top category:      {stats.get('top_category','N/A')} (${stats.get('top_category_amount',0):.2f})
- Biggest spend day: {stats.get('biggest_expense_day','N/A')}

── BY CATEGORY ──
{_fmt_categories(stats)}

── TOP MERCHANTS ──
{_fmt_merchants(stats)}

── BUDGETS ──
{_fmt_budgets(budgets)}

{recent_ctx}

{recurring_ctx}

USER'S QUESTION: {safe_msg}"""

    result = groq_generate(prompt)
    if "unavailable" in result.lower():
        return _rule_based_chat(safe_msg, stats, budgets)
    return result


class PlaidFetchError(Exception):
    def __init__(self, flask_response):
        self.flask_response = flask_response


def _fetch_all_transactions(access_token, days):
    end_date   = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    try:
        first  = plaid_client.transactions_get(
            TransactionsGetRequest(access_token=access_token, start_date=start_date, end_date=end_date,
                                   options=TransactionsGetRequestOptions(count=500, offset=0))
        )
        all_tx = list(first.transactions)
        total  = first.total_transactions
        pages  = 0
        while len(all_tx) < total:
            pages += 1
            if pages > 20:
                logger.warning("Pagination cap: fetched %d of %d", len(all_tx), total)
                break
            resp    = plaid_client.transactions_get(
                TransactionsGetRequest(access_token=access_token, start_date=start_date, end_date=end_date,
                                       options=TransactionsGetRequestOptions(count=500, offset=len(all_tx)))
            )
            fetched = list(resp.transactions)
            if not fetched:
                break
            all_tx.extend(fetched)
        return [tx.to_dict() for tx in all_tx]
    except ApiException as e:
        raise PlaidFetchError(handle_plaid_exception(e))
    except Exception:
        logger.exception("Unexpected error fetching Plaid transactions")
        raise


def _get_transactions(user_id, access_token, days):
    if SIMULATION_MODE or not access_token or access_token == "fake-access-token":
        return generate_fake_transactions(days=days, num_transactions=90)
    return _fetch_all_transactions(access_token, days)


def _resolve_transactions(user_id, access_token, days):
    try:
        return _get_transactions(user_id, access_token, days), None
    except PlaidFetchError as e:
        return None, e.flask_response
    except ValueError as e:
        return None, _error(400, str(e))
    except Exception:
        logger.exception("Error resolving transactions user=%s", user_id)
        return None, _error(500, "Internal server error")


@app.route("/")
def home():
    return _ok(app="Domus -- Flask + Plaid + Groq AI", version="4.0",
               simulation_mode=SIMULATION_MODE,
               endpoints=[
                   "POST /create_link_token","POST /exchange_token","POST /sandbox/init","GET /accounts",
                   "GET /transactions","GET /report","GET /alert","GET /recurring",
                   "GET /anomalies","POST /budgets/auto","POST /budgets/set",
                   "GET /budgets","POST /chat","GET /history",
                   "POST /simulate","POST /reset","GET /health"])


@app.route("/today", methods=["GET"])
@require_auth
def today_summary():
    user_id = get_user_id()
    access_token, _ = load_token(user_id)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, 90)
    if err_resp: return err_resp

    today_date = datetime.now(timezone.utc).date()
    today_str  = today_date.strftime("%Y-%m-%d")
    week_start = (today_date - timedelta(days=today_date.weekday())).strftime("%Y-%m-%d")

    # Today's and this-week's spending
    today_spent = sum(float(tx.get("amount", 0) or 0) for tx in all_tx
                      if str(tx.get("date", "")) == today_str and float(tx.get("amount", 0) or 0) > 0)
    week_spent  = sum(float(tx.get("amount", 0) or 0) for tx in all_tx
                      if str(tx.get("date", "")) >= week_start and float(tx.get("amount", 0) or 0) > 0)

    # Recent 5 transactions
    recent = sorted([tx for tx in all_tx if float(tx.get("amount", 0) or 0) > 0],
                    key=lambda x: str(x.get("date", "")), reverse=True)[:5]
    recent_simple = [{"name":    tx.get("merchant_name") or tx.get("name") or "Unknown",
                      "amount":  round(float(tx.get("amount", 0) or 0), 2),
                      "date":    str(tx.get("date", "")),
                      "category": _tx_category(tx)} for tx in recent]

    # Upcoming bills: recurring merchants + estimated next due date
    recurring = detect_recurring_transactions(all_tx)
    merchant_last = {}
    for tx in all_tx:
        nm  = (tx.get("merchant_name") or tx.get("name") or "").strip()
        key = re.sub(r'[\s\d#*]+$', '', nm.lower()).strip()
        ds  = str(tx.get("date", ""))
        if key and ds and (key not in merchant_last or ds > merchant_last[key][0]):
            merchant_last[key] = (ds, tx)

    upcoming = []
    for r in recurring:
        nm  = r["merchant"]
        key = re.sub(r'[\s\d#*]+$', '', nm.lower()).strip()
        info = merchant_last.get(key)
        if not info:
            continue
        try:
            last_d    = datetime.strptime(info[0], "%Y-%m-%d").date()
            next_due  = last_d + timedelta(days=30)
            days_away = (next_due - today_date).days
            if -5 <= days_away <= 35:
                upcoming.append({"merchant":   nm,
                                 "amount":     r["avg_amount"],
                                 "due_date":   next_due.strftime("%Y-%m-%d"),
                                 "days_until": days_away,
                                 "category":   r["category"],
                                 "subscription": r["is_subscription"]})
        except (ValueError, TypeError):
            continue

    upcoming.sort(key=lambda x: x["days_until"])
    return _ok(today_date=today_str,
               today_spent=round(today_spent, 2),
               week_spent=round(week_spent, 2),
               recent_transactions=recent_simple,
               upcoming_bills=upcoming[:8])


@app.route("/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error",
                    "simulation_mode": SIMULATION_MODE, "groq": "ok" if groq_client else "disabled",
                    "timestamp": datetime.now(timezone.utc).isoformat()}), (200 if db_ok else 503)


@app.route("/create_link_token", methods=["POST"])
@require_auth
def create_link_token():
    user_id = get_user_id()
    if SIMULATION_MODE:
        return _ok(link_token="fake-link-token-for-testing", simulation_mode=True)
    try:
        req  = LinkTokenCreateRequest(user=LinkTokenCreateRequestUser(client_user_id=user_id),
                                      client_name="Domus", products=[Products("transactions")],
                                      country_codes=[CountryCode("US")], language="en")
        resp = plaid_client.link_token_create(req)
        return _ok(link_token=resp.link_token)
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /create_link_token")
        return _error(500, "Internal server error")


@app.route("/exchange_token", methods=["POST"])
@require_auth
def exchange_token():
    user_id      = get_user_id()
    public_token = (request.json or {}).get("public_token", "")
    if not isinstance(public_token, str) or not public_token.strip():
        return _error(400, "Missing or invalid public_token")
    public_token = public_token.strip()
    if SIMULATION_MODE or public_token == "fake-public-token":
        save_token(user_id, "fake-access-token", "fake-item-id")
        return _ok(message="Bank connected (simulation mode)", simulation_mode=True)
    try:
        resp = plaid_client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token))
        save_token(user_id, resp.access_token, resp.item_id)
        return _ok(message="Bank connected successfully")
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /exchange_token")
        return _error(500, "Internal server error")


@app.route("/sandbox/init", methods=["POST"])
@require_auth
def sandbox_init():
    """Auto-connect a Plaid sandbox institution without going through Link UI."""
    user_id = get_user_id()
    # If already connected with a real token, skip
    existing_token, _ = load_token(user_id)
    if existing_token and existing_token != "fake-access-token":
        return _ok(message="Already connected to sandbox", already_connected=True)
    if SIMULATION_MODE:
        save_token(user_id, "fake-access-token", "fake-item-id")
        return _ok(message="Simulation mode — using demo data", simulation_mode=True)
    try:
        # Create a sandbox public token for Chase (ins_109508)
        pt_resp = plaid_client.sandbox_public_token_create(
            SandboxPublicTokenCreateRequest(
                institution_id="ins_109508",
                initial_products=[Products("transactions")],
            )
        )
        # Exchange it for a real sandbox access token
        ex_resp = plaid_client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=pt_resp.public_token)
        )
        save_token(user_id, ex_resp.access_token, ex_resp.item_id)
        return _ok(message="Sandbox bank connected automatically")
    except ApiException as e:
        logger.warning("Sandbox init Plaid error — falling back to demo data: %s", e)
        save_token(user_id, "fake-access-token", "fake-item-id")
        return _ok(message="Using demo data (Plaid sandbox unavailable)", simulation_mode=True)
    except Exception:
        logger.exception("Unexpected error in /sandbox/init")
        save_token(user_id, "fake-access-token", "fake-item-id")
        return _ok(message="Using demo data", simulation_mode=True)


@app.route("/accounts", methods=["GET"])
@require_auth
def get_accounts():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    if SIMULATION_MODE or not access_token or access_token == "fake-access-token":
        return _ok(accounts=generate_fake_accounts(), simulation_mode=True)
    try:
        resp = plaid_client.accounts_get(AccountsGetRequest(access_token=access_token))
        return _ok(accounts=[a.to_dict() for a in resp.accounts])
    except ApiException as e:
        return handle_plaid_exception(e)
    except Exception:
        logger.exception("Unexpected error in /accounts")
        return _error(500, "Internal server error")


@app.route("/transactions", methods=["GET"])
@require_auth
def get_transactions():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    days,      err = validate_int_param(request.args.get("days"),       30, 1,       730)
    if err: return _error(400, err)
    page_size, err = validate_int_param(request.args.get("page_size"),  20, 1,       500)
    if err: return _error(400, err)
    offset,    err = validate_int_param(request.args.get("offset"),      0, 0, 100_000)
    if err: return _error(400, err)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    stats = calculate_stats(all_tx)
    page  = all_tx[offset: offset + page_size]
    data  = dict(transactions=page, total_transactions=len(all_tx), offset=offset,
                 page_size=page_size, has_more=(offset + page_size) < len(all_tx), stats=stats)
    if SIMULATION_MODE or access_token == "fake-access-token":
        data["simulation_mode"] = True
    return _ok(**data)


@app.route("/report", methods=["GET"])
@require_auth
def get_report():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    days, err = validate_int_param(request.args.get("days"), 30, 1, 730)
    if err: return _error(400, err)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    stats = calculate_stats(all_tx)
    if not stats:
        return _error(400, "No transaction data available for the requested period")
    budgets     = load_budgets(user_id)
    report_text = groq_spending_report(stats, budgets, days)
    save_report(user_id, "full_report", report_text, stats)
    return _ok(report=report_text, stats=stats, period_days=days,
               generated_at=datetime.now(timezone.utc).isoformat())


@app.route("/alert", methods=["GET"])
@require_auth
def get_alert():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    days, err = validate_int_param(request.args.get("days"), 30, 1, 730)
    if err: return _error(400, err)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    stats = calculate_stats(all_tx)
    if not stats:
        return _error(400, "No transaction data available for the requested period")
    budgets    = load_budgets(user_id)
    alert_text = groq_alert(stats, budgets)
    save_report(user_id, "alert", alert_text, stats)
    return _ok(alert=alert_text, budgets=budgets,
               stats_summary={"total_spent": stats["total_spent"], "net_cash_flow": stats["net_cash_flow"]})


@app.route("/budgets/auto", methods=["POST"])
@require_auth
def auto_set_budgets():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    body         = request.json or {}
    days, err    = validate_int_param(body.get("days"), 30, 1, 730)
    if err: return _error(400, err)
    overwrite_user = bool(body.get("overwrite_user_budgets", False))
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    stats = calculate_stats(all_tx)
    if not stats:
        return _error(400, "No transaction data available")
    recommended = groq_budget_recommendations(stats)
    if not recommended:
        return _error(500, "AI could not generate budgets -- please try again")
    existing       = load_budgets(user_id)
    saved, skipped = [], []
    for category, limit in recommended.items():
        if existing.get(category, {}).get("set_by") == "user" and not overwrite_user:
            skipped.append(category)
            continue
        save_budget(user_id, category, float(limit), set_by="ai")
        saved.append(category)
    return _ok(message=f"AI set {len(saved)} budget(s).",
               budgets_set=saved, budgets_skipped=skipped, recommended=recommended)


@app.route("/budgets/set", methods=["POST"])
@require_auth
def set_budget_manual():
    user_id  = get_user_id()
    body     = request.json or {}
    category = body.get("category", "")
    limit    = body.get("monthly_limit")
    if not category or not isinstance(category, str):
        return _error(400, "Missing or invalid 'category'")
    category = sanitize_text(category, _MAX_CATEGORY_LEN)
    if not category:
        return _error(400, "Category cannot be empty")
    if limit is None:
        return _error(400, "Missing 'monthly_limit'")
    try:
        limit = float(limit)
        if limit < 0 or limit > 1_000_000:
            raise ValueError
    except (TypeError, ValueError):
        return _error(400, "monthly_limit must be a number between 0 and 1,000,000")
    save_budget(user_id, category, limit, set_by="user")
    return _ok(message=f"Budget for '{category}' set to ${limit:.2f}/month")


@app.route("/budgets", methods=["GET"])
@require_auth
def get_budgets():
    return _ok(budgets=load_budgets(get_user_id()))


@app.route("/chat", methods=["POST"])
@require_auth
def chat():
    user_id = get_user_id()
    body    = request.json or {}
    message = body.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return _error(400, "Missing or empty 'message'")
    message = sanitize_text(message, _MAX_CHAT_MESSAGE_LEN)
    if not message:
        return _error(400, "Message cannot be empty after sanitization")
    access_token, _ = load_token(user_id)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, 30)
    if err_resp: return err_resp
    stats = calculate_stats(all_tx)
    if not stats:
        return _error(400, "No transaction data available")
    budgets = load_budgets(user_id)
    reply   = groq_chat(message, stats, budgets, all_tx=all_tx)
    return _ok(reply=reply, message=message)


@app.route("/history", methods=["GET"])
@require_auth
def get_history():
    user_id    = get_user_id()
    limit, err = validate_int_param(request.args.get("limit"), 5, 1, 50)
    if err: return _error(400, err)
    history = load_report_history(user_id, limit=limit)
    return _ok(history=history, count=len(history))


@app.route("/recurring", methods=["GET"])
@require_auth
def get_recurring():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    days, err = validate_int_param(request.args.get("days"), 90, 1, 730)
    if err: return _error(400, err)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    recurring = detect_recurring_transactions(all_tx)
    return _ok(recurring=recurring, count=len(recurring), period_days=days)


@app.route("/anomalies", methods=["GET"])
@require_auth
def get_anomalies():
    user_id      = get_user_id()
    access_token, _ = load_token(user_id)
    days, err = validate_int_param(request.args.get("days"), 30, 1, 730)
    if err: return _error(400, err)
    threshold, err = validate_int_param(request.args.get("threshold"), 2, 1, 10)
    if err: return _error(400, err)
    all_tx, err_resp = _resolve_transactions(user_id, access_token, days)
    if err_resp: return err_resp
    anomalies = detect_anomalies(all_tx, threshold=float(threshold))
    return _ok(anomalies=anomalies, count=len(anomalies), period_days=days, threshold=threshold)


@app.route("/simulate", methods=["POST"])
@require_auth
def simulate():
    user_id = get_user_id()
    body    = request.json or {}
    days_val,   err = validate_int_param(body.get("days"),            30, 1, 730)
    if err: return _error(400, err)
    num_tx_val, err = validate_int_param(body.get("num_transactions"), 90, 1, 500)
    if err: return _error(400, err)
    save_token(user_id, "fake-access-token", "fake-item-id")
    fake_tx = generate_fake_transactions(days=days_val, num_transactions=num_tx_val)
    return _ok(message="Simulation data generated", stats={"accounts": 3, "transactions": len(fake_tx)})


@app.route("/reset", methods=["POST"])
@require_auth
def reset():
    delete_token(get_user_id())
    return _ok(message="Bank disconnected")


@app.errorhandler(400)
def bad_request(_e):    return _error(400, "Bad request")

@app.errorhandler(401)
def unauthorized(_e):   return _error(401, "Unauthorized")

@app.errorhandler(404)
def not_found(_e):      return _error(404, "Endpoint not found")

@app.errorhandler(405)
def method_not_allowed(_e): return _error(405, "Method not allowed")

@app.errorhandler(413)
def request_too_large(_e):  return _error(413, "Request body too large (max 64 KB)")

@app.errorhandler(500)
def server_error(_e):   return _error(500, "Internal server error")


if __name__ == "__main__":
    print("=" * 60)
    print("  Domus -- Flask + Plaid + Groq AI  v4.0")
    print("=" * 60)
    print(f"  Plaid environment : {PLAID_ENV}")
    print(f"  Simulation mode   : {SIMULATION_MODE}")
    print(f"  Groq AI           : {'Ready' if groq_client else 'Disabled (set GROQ_API_KEY)'}")
    print(f"  Auth              : {'API_KEY set' if API_KEY else 'DISABLED (set API_KEY in .env)'}")
    print(f"  Token storage     : {DB_PATH}")
    print("=" * 60)
    app.run(debug=(PLAID_ENV == "sandbox"), port=5000)
