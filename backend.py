import os
from flask import Flask, jsonify, request
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid.model import *

app = Flask(__name__)

# -----------------------------
# CONFIG & INITIALIZATION
# -----------------------------

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    raise Exception("Plaid environment variables not set")

configuration = Configuration(
    host="https://sandbox.plaid.com",
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    }
)

api_client = ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)

# -----------------------------
# SIMPLE IN-MEMORY STORAGE
# (learning only)
# -----------------------------

db = {
    "access_token": None,
    "item_id": None,
    "status": "not_connected"
}

# -----------------------------
# BASIC AI FUNDAMENTALS (V1)
# -----------------------------

def analyze_transactions(transactions):
    """
    VERY basic AI logic (rule-based for now).
    Later this becomes ML / LLM / agent-based.
    """
    total_spent = 0
    categories = {}

    for tx in transactions:
        amount = tx["amount"]
        total_spent += amount

        category = tx["category"][0] if tx.get("category") else "Other"
        categories[category] = categories.get(category, 0) + amount

    insight = {
        "total_spent": round(total_spent, 2),
        "top_category": max(categories, key=categories.get) if categories else None,
        "category_breakdown": categories
    }

    return insight

# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def home():
    return jsonify({
        "app": "Flask + Plaid Sandbox",
        "connection_status": db["status"]
    })


# STEP 1: Create Link Token
@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    try:
        request_data = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id="test_user"
            ),
            client_name="AI Cash Manager",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en"
        )

        response = plaid_client.link_token_create(request_data)
        return jsonify({"success": True, "link_token": response["link_token"]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# STEP 2: Exchange public_token → access_token
@app.route("/exchange_token", methods=["POST"])
def exchange_token():
    try:
        public_token = request.json.get("public_token")
        if not public_token:
            return jsonify({"success": False, "error": "Missing public_token"}), 400

        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=public_token
        )

        response = plaid_client.item_public_token_exchange(exchange_request)

        db["access_token"] = response["access_token"]
        db["item_id"] = response["item_id"]
        db["status"] = "connected"

        return jsonify({
            "success": True,
            "message": "Bank connected successfully"
        })

    except Exception as e:
        db["status"] = "failed"
        return jsonify({"success": False, "error": str(e)}), 500


# STEP 3: Get account details
@app.route("/accounts", methods=["GET"])
def get_accounts():
    if not db["access_token"]:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    try:
        request_data = AccountsGetRequest(
            access_token=db["access_token"]
        )

        response = plaid_client.accounts_get(request_data)
        return jsonify({"success": True, "accounts": response["accounts"]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# STEP 4: Get transactions + AI analysis
@app.route("/transactions", methods=["GET"])
def get_transactions():
    if not db["access_token"]:
        return jsonify({"success": False, "error": "Bank not connected"}), 400

    try:
        request_data = TransactionsGetRequest(
            access_token=db["access_token"],
            start_date="2024-01-01",
            end_date="2024-12-31"
        )

        response = plaid_client.transactions_get(request_data)
        transactions = response["transactions"]

        # AI FUNDAMENTALS HERE
        insights = analyze_transactions(transactions)

        return jsonify({
            "success": True,
            "transactions": transactions,
            "ai_insights": insights
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# -----------------------------
# RUN SERVER
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True)
