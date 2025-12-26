from flask import Flask
from plaid.api import plaid_api
from plaid.configuration import Configuration 
from plaid.api_client import ApiClient
from plaid.model import *


# Initialize Flask
app = Flask(__name__)

# Initialize Plaid
configuration = Configuration(
    host = "https://sandbox.plaid.com",
    api_key = {
        "clientId: "694d8b12168aa50020a89154",
        "secret": "50c7c2d1d7ce151033bd8ffa40f7b7",

    }
)

api_client = ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)

@app.route("/")
def home():
    return "Flask and Plaid initialized"
# Create Link Token
@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    request_data = LinkTokenCreateRequest(
        user=LinkTokenCreateRequest(
            client_user_id="test_user"
        ),
        client_name="Plaid Sandbox Dashboard",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en"
    ) 

    response = plaid_client.link_token_create(request_data)
    return jsonify(response.to_dict())
if __name__ == "__main__":
    app.run(debug=True)  

# Exchange publix token --> access_token
@app.route("/exhange_token", methods=["POST"])
def exchange_token():
    global ACCESS_TOKEN

    public_token = request.json["public token"]

    exchange_request = ItemPublicTokenExchangeRequest(
        public_token=public_token

    )

    response = plaid.client.item_public_token_exchange(exchange_request)
    ACCESS_TOKEN = response["access_token"]

    return jsonify({"status": "access token started"})

# Get fake account details
@app.route("/accounts", methods=["GET"])
def get_accounts():
    if not ACCESS_TOKEN:
        return jsonify({"error": "Access token not available"})
    request_data = AccountsGetRequest(
        access_token=ACCESS_TOKEN
    )

    response = plaid.client.accounts_get(request_data)
    return jsonify(response.to_dict())

# STEP 4: Get fake transactions
@app.route("/transactions", methods=["GET"])
def get_transactions():
    if not ACCESS_TOKEN:
        return jsonify({"error": "No access token"}), 400
    
    request_data = TransactionsGetRequest(
        access_token=ACCESS_TOKEN
        start_date="2025-11-26",
        end_date="2025-11-27"
    )

    response = plaid.client.transactions_get(request_data)
    return jsonify(response.to_dict())

if _name_ == "__main__":
    app.run(debug=True)
