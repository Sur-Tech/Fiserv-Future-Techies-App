import os
import random
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Plaid imports
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend testing

# -----------------------------
# CONFIG & INITIALIZATION
# -----------------------------

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    print("WARNING: Plaid environment variables not set. Running in simulation mode only.")
    SIMULATION_MODE = True
else:
    SIMULATION_MODE = False
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
    "status": "not_connected",
    "accounts": [],
    "transactions": []
}

# -----------------------------
# FAKE DATA GENERATORS
# -----------------------------

def generate_fake_accounts():
    """Generate realistic fake accounts for testing"""
    accounts = [
        {
            "account_id": "fake_checking_001",
            "balances": {
                "available": 2500.50,
                "current": 2500.50,
                "limit": None,
                "iso_currency_code": "USD"
            },
            "mask": "4321",
            "name": "Plaid Checking",
            "official_name": "Plaid Silver Standard 0.1% Interest Checking",
            "subtype": "checking",
            "type": "depository"
        },
        {
            "account_id": "fake_savings_001",
            "balances": {
                "available": 10000.00,
                "current": 10000.00,
                "limit": None,
                "iso_currency_code": "USD"
            },
            "mask": "5678",
            "name": "Plaid Saving",
            "official_name": "Plaid Bronze Standard 0.2% Interest Saving",
            "subtype": "savings",
            "type": "depository"
        },
        {
            "account_id": "fake_credit_001",
            "balances": {
                "available": 3500.00,
                "current": 1500.00,
                "limit": 5000,
                "iso_currency_code": "USD"
            },
            "mask": "9012",
            "name": "Plaid Credit Card",
            "official_name": "Plaid Diamond 12.5% APR Interest Credit Card",
            "subtype": "credit card",
            "type": "credit"
        }
    ]
    return accounts

def generate_fake_transactions(days=30, num_transactions=90):
    """Generate realistic fake transactions for testing"""
    
    merchants_by_category = {
        "Food and Drink": [
            ("Starbucks", 4.50, 8.00),
            ("McDonald's", 8.00, 15.00),
            ("Chipotle", 10.00, 18.00),
            ("Whole Foods", 30.00, 120.00),
            ("Trader Joe's", 25.00, 80.00),
            ("Local Coffee Shop", 3.50, 7.00),
            ("Pizza Hut", 15.00, 35.00),
            ("Subway", 7.00, 12.00)
        ],
        "Transportation": [
            ("Uber", 8.00, 35.00),
            ("Lyft", 7.00, 30.00),
            ("Shell Gas Station", 30.00, 60.00),
            ("Chevron", 35.00, 65.00),
            ("Parking Meter", 2.00, 10.00),
            ("Public Transit", 2.50, 5.00)
        ],
        "Shopping": [
            ("Amazon", 10.00, 200.00),
            ("Target", 15.00, 150.00),
            ("Walmart", 20.00, 180.00),
            ("Best Buy", 25.00, 500.00),
            ("Nike Store", 50.00, 200.00),
            ("Apple Store", 20.00, 2000.00)
        ],
        "Entertainment": [
            ("Netflix", 15.99, 15.99),
            ("Spotify", 9.99, 9.99),
            ("AMC Theaters", 12.00, 30.00),
            ("Steam Games", 5.00, 60.00),
            ("PlayStation Store", 10.00, 70.00)
        ],
        "Bills & Utilities": [
            ("Electric Company", 80.00, 150.00),
            ("Internet Provider", 59.99, 59.99),
            ("Water Company", 30.00, 50.00),
            ("Phone Bill", 45.00, 85.00),
            ("Insurance", 100.00, 200.00)
        ],
        "Healthcare": [
            ("CVS Pharmacy", 10.00, 50.00),
            ("Walgreens", 8.00, 45.00),
            ("Doctor's Office", 25.00, 200.00),
            ("Dentist", 50.00, 300.00)
        ],
        "Transfer": [
            ("Venmo", 10.00, 100.00),
            ("PayPal", 5.00, 200.00),
            ("Zelle Payment", 20.00, 150.00)
        ]
    }
    
    transactions = []
    
    # Generate transactions spread across the time period
    for i in range(num_transactions):
        # Random date within the specified range
        days_ago = random.randint(0, days)
        transaction_date = datetime.now() - timedelta(days=days_ago)
        
        # Pick a category and merchant
        category = random.choice(list(merchants_by_category.keys()))
        merchant_data = random.choice(merchants_by_category[category])
        merchant_name = merchant_data[0]
        min_amount = merchant_data[1]
        max_amount = merchant_data[2]
        
        # Generate amount
        amount = round(random.uniform(min_amount, max_amount), 2)
        
        # Some transactions might be pending (recent ones)
        pending = days_ago <= 2 and random.random() < 0.3
        
        transaction = {
            "transaction_id": f"fake_tx_{i:04d}",
            "account_id": random.choice(["fake_checking_001", "fake_credit_001"]),
            "amount": amount,
            "iso_currency_code": "USD",
            "category": [category],
            "category_id": f"{category.lower().replace(' ', '_')}_id",
            "date": transaction_date.strftime("%Y-%m-%d"),
            "authorized_date": transaction_date.strftime("%Y-%m-%d"),
            "name": merchant_name.upper(),
            "merchant_name": merchant_name,
            "payment_channel": random.choice(["in store", "online", "other"]),
            "pending": pending,
            "pending_transaction_id": None,
            "personal_finance_category": {
                "primary": category,
                "detailed": f"{category}_{merchant_name.lower().replace(' ', '_')}"
            },
            "transaction_type": "place"
        }
        
        transactions.append(transaction)
    
    # Sort by date (most recent first)
    return sorted(transactions, key=lambda x: x["date"], reverse=True)

# -----------------------------
# AI ANALYSIS FUNCTIONS
# -----------------------------

def analyze_transactions(transactions):
    """
    Enhanced AI logic for transaction analysis.
    This is still rule-based but more sophisticated.
    """
    if not transactions:
        return {
            "error": "No transactions to analyze",
            "suggestions": ["Connect a bank account to see insights"]
        }
    
    total_spent = 0
    total_income = 0
    categories = {}
    merchants = {}
    daily_spending = {}
    
    for tx in transactions:
        amount = tx["amount"]
        date = tx["date"]
        merchant = tx.get("merchant_name", tx.get("name", "Unknown"))
        
        # Track spending vs income
        if amount > 0:
            total_spent += amount
        else:
            total_income += abs(amount)
        
        # Category breakdown
        if tx.get("category"):
            category = tx["category"][0] if isinstance(tx["category"], list) else tx["category"]
        else:
            category = "Other"
        
        categories[category] = categories.get(category, 0) + amount
        
        # Merchant frequency
        merchants[merchant] = merchants.get(merchant, {"count": 0, "total": 0})
        merchants[merchant]["count"] += 1
        merchants[merchant]["total"] += amount
        
        # Daily spending patterns
        daily_spending[date] = daily_spending.get(date, 0) + amount
    
    # Calculate averages and identify patterns
    avg_daily_spend = round(total_spent / len(daily_spending), 2) if daily_spending else 0
    
    # Find top merchants by frequency
    top_merchants = sorted(
        [(m, data["count"], data["total"]) for m, data in merchants.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    # Find biggest expense categories
    sorted_categories = sorted(
        categories.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    # Generate insights and recommendations
    insights = {
        "summary": {
            "total_spent": round(total_spent, 2),
            "total_income": round(total_income, 2),
            "net_cash_flow": round(total_income - total_spent, 2),
            "transaction_count": len(transactions),
            "avg_transaction": round(total_spent / len(transactions), 2) if transactions else 0,
            "avg_daily_spend": avg_daily_spend
        },
        "categories": {
            "breakdown": {cat: round(amount, 2) for cat, amount in sorted_categories},
            "top_category": sorted_categories[0][0] if sorted_categories else None,
            "top_category_amount": round(sorted_categories[0][1], 2) if sorted_categories else 0
        },
        "merchants": {
            "most_frequent": [
                {
                    "name": m[0],
                    "visits": m[1],
                    "total_spent": round(m[2], 2)
                } for m in top_merchants
            ]
        },
        "patterns": {
            "spending_trend": "increasing" if len(transactions) > 10 and 
                            sum(tx["amount"] for tx in transactions[:5]) > 
                            sum(tx["amount"] for tx in transactions[5:10]) else "stable",
            "biggest_expense_day": max(daily_spending.items(), key=lambda x: x[1])[0] 
                                  if daily_spending else None
        },
        "recommendations": generate_recommendations(categories, total_spent, avg_daily_spend)
    }
    
    return insights

def generate_recommendations(categories, total_spent, avg_daily_spend):
    """Generate AI-powered recommendations based on spending patterns"""
    recommendations = []
    
    # Check food spending
    food_spending = categories.get("Food and Drink", 0)
    if food_spending > total_spent * 0.3:
        recommendations.append({
            "category": "Food & Drink",
            "insight": f"You're spending {round(food_spending/total_spent*100, 1)}% on food",
            "suggestion": "Consider meal planning or cooking at home more often"
        })
    
    # Check transportation
    transport_spending = categories.get("Transportation", 0)
    if transport_spending > total_spent * 0.2:
        recommendations.append({
            "category": "Transportation",
            "insight": f"Transportation is {round(transport_spending/total_spent*100, 1)}% of spending",
            "suggestion": "Look into public transit passes or carpooling options"
        })
    
    # Daily spending advice
    if avg_daily_spend > 100:
        recommendations.append({
            "category": "Daily Budget",
            "insight": f"You're spending an average of ${avg_daily_spend} per day",
            "suggestion": "Set a daily spending limit to better control expenses"
        })
    
    # Shopping patterns
    shopping_spending = categories.get("Shopping", 0)
    if shopping_spending > total_spent * 0.25:
        recommendations.append({
            "category": "Shopping",
            "insight": "Shopping represents a significant portion of your expenses",
            "suggestion": "Try the 24-hour rule before making non-essential purchases"
        })
    
    return recommendations

# -----------------------------
# ROUTES
# -----------------------------

@app.route("/")
def home():
    return jsonify({
        "app": "Flask + Plaid Transaction Simulator",
        "version": "1.0",
        "connection_status": db["status"],
        "simulation_mode": SIMULATION_MODE,
        "endpoints": [
            "/create_link_token - Create Plaid Link token",
            "/exchange_token - Exchange public token",
            "/accounts - Get bank accounts",
            "/transactions - Get transactions with AI insights",
            "/simulate - Generate fake data for testing"
        ]
    })

@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    """Create a Link token for Plaid connection"""
    
    if SIMULATION_MODE:
        # Return a fake token for testing
        return jsonify({
            "success": True,
            "link_token": "fake-link-token-for-testing",
            "simulation_mode": True
        })
    
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
        return jsonify({
            "success": True,
            "link_token": response["link_token"]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/exchange_token", methods=["POST"])
def exchange_token():
    """Exchange public token for access token"""
    
    public_token = request.json.get("public_token")
    
    if SIMULATION_MODE or public_token == "fake-public-token":
        # Simulate successful connection
        db["access_token"] = "fake-access-token"
        db["item_id"] = "fake-item-id"
        db["status"] = "connected"
        db["accounts"] = generate_fake_accounts()
        db["transactions"] = generate_fake_transactions()
        
        return jsonify({
            "success": True,
            "message": "Bank connected successfully (simulation mode)",
            "simulation_mode": True
        })
    
    if not public_token:
        return jsonify({
            "success": False,
            "error": "Missing public_token"
        }), 400

    try:
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
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/accounts", methods=["GET"])
def get_accounts():
    """Get all connected bank accounts"""
    
    # Check if we're in simulation mode or have fake data
    if SIMULATION_MODE or db["access_token"] == "fake-access-token":
        if not db["accounts"]:
            db["accounts"] = generate_fake_accounts()
        
        return jsonify({
            "success": True,
            "accounts": db["accounts"],
            "simulation_mode": True
        })
    
    if not db["access_token"]:
        return jsonify({
            "success": False,
            "error": "Bank not connected"
        }), 400

    try:
        request_data = AccountsGetRequest(
            access_token=db["access_token"]
        )

        response = plaid_client.accounts_get(request_data)
        db["accounts"] = response["accounts"]
        
        return jsonify({
            "success": True,
            "accounts": response["accounts"]
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/transactions", methods=["GET"])
def get_transactions():
    """Get transactions with AI analysis"""
    
    # Get query parameters
    days = request.args.get("days", 30, type=int)
    
    # Check if we're in simulation mode or have fake data
    if SIMULATION_MODE or db["access_token"] == "fake-access-token":
        if not db["transactions"]:
            db["transactions"] = generate_fake_transactions(days=days)
        
        insights = analyze_transactions(db["transactions"])
        
        return jsonify({
            "success": True,
            "transactions": db["transactions"][:50],  # Return first 50 transactions
            "ai_insights": insights,
            "simulation_mode": True,
            "total_transactions": len(db["transactions"])
        })
    
    if not db["access_token"]:
        return jsonify({
            "success": False,
            "error": "Bank not connected"
        }), 400

    try:
        # Calculate date range
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        request_data = TransactionsGetRequest(
            access_token=db["access_token"],
            start_date=start_date,
            end_date=end_date
        )

        response = plaid_client.transactions_get(request_data)
        transactions = response["transactions"]
        
        # If no real transactions, generate fake ones
        if not transactions:
            transactions = generate_fake_transactions(days=days)
            
        # Store transactions
        db["transactions"] = transactions
        
        # AI analysis
        insights = analyze_transactions(transactions)

        return jsonify({
            "success": True,
            "transactions": transactions[:50],  # Return first 50 transactions
            "ai_insights": insights,
            "total_transactions": len(transactions)
        })

    except Exception as e:
        # On error, return fake data
        transactions = generate_fake_transactions(days=days)
        insights = analyze_transactions(transactions)
        
        return jsonify({
            "success": True,
            "transactions": transactions[:50],
            "ai_insights": insights,
            "simulation_mode": True,
            "error": str(e),
            "note": "Using simulated data due to API error"
        })

@app.route("/simulate", methods=["POST"])
def simulate():
    """Force simulation mode for testing"""
    
    # Generate all fake data
    db["status"] = "connected"
    db["access_token"] = "fake-access-token"
    db["item_id"] = "fake-item-id"
    db["accounts"] = generate_fake_accounts()
    db["transactions"] = generate_fake_transactions(
        days=request.json.get("days", 30),
        num_transactions=request.json.get("num_transactions", 90)
    )
    
    return jsonify({
        "success": True,
        "message": "Simulation data generated",
        "stats": {
            "accounts": len(db["accounts"]),
            "transactions": len(db["transactions"])
        }
    })

@app.route("/reset", methods=["POST"])
def reset():
    """Reset the database"""
    global db
    db = {
        "access_token": None,
        "item_id": None,
        "status": "not_connected",
        "accounts": [],
        "transactions": []
    }
    
    return jsonify({
        "success": True,
        "message": "Database reset"
    })

# -----------------------------
# ERROR HANDLERS
# -----------------------------

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

# -----------------------------
# RUN SERVER
# -----------------------------

if __name__ == "__main__":
    print("=" * 50)
    print("AI CASH MANAGER - Transaction Simulator")
    print("=" * 50)
    
    if SIMULATION_MODE:
        print("⚠️  Running in SIMULATION MODE (no Plaid credentials found)")
        print("   Add PLAID_CLIENT_ID and PLAID_SECRET to .env file for real mode")
    else:
        print("✅ Plaid credentials found - Ready for real connections")
    
    print("\nAvailable endpoints:")
    print("  - GET  / : Home/Status")       
    print("  - POST /create_link_token : Start Plaid Link")
    print("  - POST /exchange_token : Complete connection")
    print("  - GET  /accounts : List bank accounts")
    print("  - GET  /transactions : Get transactions + AI insights")
    print("  - POST /simulate : Generate fake data")
    print("  - POST /reset : Clear all data")
    print("\nStarting server on http://localhost:5000")
    print("=" * 50)
    
    app.run(debug=True, port=5000)
