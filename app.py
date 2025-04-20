import streamlit as st
import pandas as pd
from openai import OpenAI
import pymysql
from sshtunnel import SSHTunnelForwarder
from pymongo import MongoClient
import json
import os
import time

# --- Set API Key from secrets and initialize OpenAI client ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# --- Load all datasets ---
try:
    cards_df = pd.read_csv("data/cards_data.csv", nrows=1000)
    users_df = pd.read_csv("data/users_data.csv", nrows=1000)
    Customers_df = pd.read_csv("data/Customers.csv", nrows=1000)
    Transactions_df = pd.read_csv("data/Transactions.csv", nrows=1000)

    with open("data/customers.json") as f:
        customers_data = json.load(f)
    with open("data/products.json") as f:
        products_data = json.load(f)
    with open("data/ratings.json") as f:
        ratings_data = json.load(f)

except FileNotFoundError as e:
    st.error(f"Could not load dataset: {e}")
    st.stop()

# --- Column mappings ---
cards_df_columns = list(cards_df.columns)
users_df_columns = list(users_df.columns)
Customers_df_columns = list(Customers_df.columns)
Transactions_df_columns = list(Transactions_df.columns)
customers_columns = list(customers_data[0].keys())
products_columns = list(products_data[0].keys())
ratings_columns = list(ratings_data[0].keys())

dataset_fields_map = {
    "users_df": users_df_columns,
    "cards_df": cards_df_columns,
    "Customers_df": Customers_df_columns,
    "Transactions_df": Transactions_df_columns,
    "customers_json": customers_columns,
    "products_json": products_columns,
    "ratings_json": ratings_columns
}

# --- Determine relevant datasets ---
def which_dataset(user_input, dataset_fields):
    schema_description = "\n".join([
        f"{name}: {', '.join(fields)}" for name, fields in dataset_fields.items()
    ])

    prompt = f"""
You are an expert data scientist.

Here are the available datasets and the fields they contain:
{schema_description}

The user asked:
\"{user_input}\"

Return ONLY the dataset names (like "cards_df", "users_df") as a comma-separated list. No explanation.
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

# --- Generate SQL/MongoDB query ---
def create_query(user_input):
    datasets = which_dataset(user_input, dataset_fields_map)
    datasets_list = [d.strip() for d in datasets.split(",")]

    columns_dict = {d: dataset_fields_map[d] for d in datasets_list}
    schema_description = "\n".join([f"{k}: {', '.join(v)}" for k, v in columns_dict.items()])

    prompt = f"""
You are an expert query writer.

Here are the available datasets and the fields they contain:
{schema_description}

The user asked:
\"{user_input}\"

Return ONLY a valid query. Use SQL syntax for tabular data (ending with '_df') and MongoDB syntax for JSON datasets (ending with '_json'). No explanation.
"""

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip(), datasets_list

# --- Execute SQL query via SSH tunnel ---
def execute_mysql_query(query):
    ssh_host = 'ec2-18-221-231-28.us-east-2.compute.amazonaws.com'
    ssh_user = 'ubuntu'
    ssh_key = 'dsci351.pem'  # Should exist or be created from Streamlit secrets

    mysql_host = 'localhost'
    mysql_user = 'root'
    mysql_password = 'Dsci351'
    mysql_db = 'transactions_db'

    try:
        with SSHTunnelForwarder(
            (ssh_host, 22),
            ssh_username=ssh_user,
            ssh_pkey=ssh_key,
            remote_bind_address=('127.0.0.1', 3306)
        ) as tunnel:
            print(f"Tunnel active: {tunnel.is_active}")  # Debugging line
            if tunnel.is_active:
                print("Tunnel successfully established.")
                connection = pymysql.connect(
                    host=mysql_host,
                    user=mysql_user,
                    password=mysql_password,
                    database=mysql_db,
                    port=tunnel.local_bind_port
                )
            else:
                print("Tunnel is not active.")
            with connection.cursor() as cursor:
                cursor.execute(query)

                if query.strip().lower().startswith("select"):
                    result = cursor.fetchall()
                    column_names = [desc[0] for desc in cursor.description]
                    return pd.DataFrame(result, columns=column_names)
                else:
                    connection.commit()
                    return f"Query executed successfully: `{query.split()[0].upper()}`"
    except Exception as e:
        return f"Error establishing SSH tunnel: {e}"

# --- Execute MongoDB query ---
def execute_mongo_query(query, collection_name):
    ssh_host = 'ec2-18-221-231-28.us-east-2.compute.amazonaws.com'
    ssh_user = 'ubuntu'
    ssh_key = 'dsci351.pem'  # Make sure this is securely stored
    mongo_port = 27017

    try:
        with SSHTunnelForwarder(
            (ssh_host, 22),
            ssh_username=ssh_user,
            ssh_pkey=ssh_key,
            remote_bind_address=('127.0.0.1', mongo_port),
            local_bind_address=('127.0.0.1', 27017)
        ) as tunnel:

            if tunnel.is_active:
                time.sleep(3)  # Allow tunnel to stabilize

                client = MongoClient('127.0.0.1', tunnel.local_bind_port, serverSelectionTimeoutMS=5000)
                db = client["json_db"]
                collection = db[collection_name.replace("_json", "")]

                # Safe evaluation (still potentially risky — use with caution)
                mongo_query = eval(query, {"__builtins__": None}, {})

                if isinstance(mongo_query, dict):
                    if "insertOne" in mongo_query:
                        result = collection.insert_one(mongo_query["insertOne"])
                        return f"Inserted ID: {result.inserted_id}"

                    elif "insertMany" in mongo_query:
                        result = collection.insert_many(mongo_query["insertMany"])
                        return f"Inserted IDs: {result.inserted_ids}"

                    elif "updateOne" in mongo_query:
                        result = collection.update_one(
                            mongo_query["updateOne"]["filter"], mongo_query["updateOne"]["update"]
                        )
                        return f"Matched: {result.matched_count}, Modified: {result.modified_count}"

                    elif "updateMany" in mongo_query:
                        result = collection.update_many(
                            mongo_query["updateMany"]["filter"], mongo_query["updateMany"]["update"]
                        )
                        return f"Matched: {result.matched_count}, Modified: {result.modified_count}"

                    elif "deleteOne" in mongo_query:
                        result = collection.delete_one(mongo_query["deleteOne"])
                        return f"Deleted Count: {result.deleted_count}"

                    elif "filter" in mongo_query:
                        result = list(collection.find(mongo_query["filter"], mongo_query.get("projection")).limit(100))
                        for doc in result:
                            doc["_id"] = str(doc["_id"])
                        return pd.DataFrame(result)

                    else:
                        return "Unsupported operation in MongoDB query."

                elif isinstance(mongo_query, list):  # Assume aggregation pipeline
                    result = list(collection.aggregate(mongo_query))
                    for doc in result:
                        doc["_id"] = str(doc["_id"])
                    return pd.DataFrame(result)

                else:
                    return "MongoDB query format not recognized."

            else:
                return "Failed to establish SSH tunnel."

    except Exception as e:
        return f"MongoDB Execution Error via SSH: {e}"

# --- Streamlit App ---
st.set_page_config(page_title="Natural Language → Query Interface", layout="wide")
st.title("Natural Language → SQL / MongoDB Interface")

st.markdown("Try queries like:")
st.markdown("- *Get users born in 1999*")
st.markdown("- *Find names of products that have a unit price less than 3*")
st.markdown("- *List all ratings given by customer with ID 103416*")

user_input = st.text_area("Enter your natural language query:")

if st.button("Generate and Run Query"):
    if not user_input.strip():
        st.warning("Please enter a query.")
    else:
        st.subheader("Generated Query")
        query, datasets_used = create_query(user_input)
        st.code(query)

        st.subheader("Query Results")
        if all(d.endswith("_df") for d in datasets_used):
            # Only SQL datasets used
            result = execute_mysql_query(query)
        elif all(d.endswith("_json") for d in datasets_used):
            # Only JSON datasets used
            collection_name = datasets_used[0]  # Choose the first JSON dataset
            result = execute_mongo_query(query, collection_name)
        else:
            result = "Error: Cannot mix SQL (_df) and MongoDB (_json) datasets in a single query."

        if isinstance(result, pd.DataFrame):
            st.dataframe(result)
        else:
            st.write(result)

