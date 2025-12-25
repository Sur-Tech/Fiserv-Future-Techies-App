from flask import Flask, request, jsonify
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.model import *
from plaid.api_client import ApiClient
import os

app = Flask(__name__)

configuration = Configuration(
    host="https://sandbox.plaid.com",
    api_key={
        "clientId": "PLAID_CLIENT_ID",
        "secret": "PLAID_SECRET",
    }
)

api_client = ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)

@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    request_data = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(
            client_user_id="user_123"
        ),
        client_name="AI Cash Manager",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en"
    )

    response = plaid_client.link_token_create(request_data)
    return jsonify(response.to_dict())

@app.route("/exchange_token", methods=["POST"])
def exchange_token():
    public_token = request.json["public_token"]

    exchange_request = ItemPublicTokenExchangeRequest(
        public_token=public_token
    )

    response = plaid_client.item_public_token_exchange(exchange_request)
    access_token = response["access_token"]

    return jsonify({"access_token": access_token})
@app.route("/transactions", methods=["POST"])
def transactions():
    access_token = request.json["access_token"]

    request_data = TransactionsGetRequest(
        access_token=access_token,
        start_date="2024-01-01",
        end_date="2024-12-31"
    )

    response = plaid_client.transactions_get(request_data)
    return jsonify(response.to_dict())
