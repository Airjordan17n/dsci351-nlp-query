import streamlit as st
import pandas as pd
from openai import OpenAI
import pymysql
from pymongo import MongoClient
import json
import os
import ast
import re

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

    columns_dict = {}
    for d in datasets_list:
        if d.endswith("_json"):
            renamed_fields = [f"{d}.{col}" for col in dataset_fields_map[d]]
            columns_dict[d] = renamed_fields
        else:
            columns_dict[d] = dataset_fields_map[d]
    schema_description = "\n".join([
    f"{name}: {', '.join([col.split('.')[-1] for col in fields])}" for name, fields in columns_dict.items()
    ])

    prompt = f"""
You are an expert query writer.

Here are the available datasets and the fields they contain:
{schema_description}

The user asked:
\"{user_input}\"

Rules:
- If **all** datasets end with `_df`, return an **SQL** query.
- If **all** datasets end with `_json`, return a **MongoDB** query in **valid JSON format**, suitable for PyMongo (double quotes required).
- Do not mix SQL and MongoDB in one query.

If MongoDB:
Return ONLY a valid MongoDB query in **Python dictionary/list syntax**, suitable for execution with the PyMongo library in Python.

Format:
- For `.find()`:
    {{ "filter": {{...}}, "projection": {{...}} }}
- For `.aggregate()`:
    [{{"$match": {{...}}}}, ...]
- For `.insertOne()`:
    {{ "insertOne": {{...}} }}
- For `.insertMany()`:
    {{ "insertMany": [{{...}}, {{...}}] }}
- For `.updateOne()`:
    {{ "updateOne": {{ "filter": {{...}}, "update": {{...}} }} }}
- For `.updateMany()`:
    {{ "updateMany": {{ "filter": {{...}}, "update": {{...}} }} }}
- For `.deleteOne()`:
    {{ "deleteOne": {{...}} }}

DO NOT return raw Mongo shell syntax or explanation — only the query object itself.

If SQL: 
Return ONLY a valid **MySQL** query using SQL syntax — no explanation, no markdown, no comments, no need to say it is sql query.
"""

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    raw_response = response.choices[0].message.content.strip()
    query_str = re.sub(r"^```(?:json)?|```$", "", raw_response.strip(), flags=re.MULTILINE).strip()

    # Now handle both SQL and MongoDB query types
    is_nosql = all(d.endswith("_json") for d in datasets_list)
    try:
        if is_nosql: 
            query_obj = ast.literal_eval(query_str)
        
            if isinstance(query_obj, list):
                query = query_obj  # Aggregation pipeline
            elif isinstance(query_obj, dict):
                if "aggregate" in query_obj:  # Embedded aggregation
                    query = query_obj["aggregate"]
                elif "filter" in query_obj or "projection" in query_obj:  # Find query
                    filter_dict = query_obj.get("filter", {})
                    projection_dict = query_obj.get("projection", None)
                    query = {"filter": filter_dict, "projection": projection_dict}
                else:
                    # Handle insertOne, updateOne, deleteOne, etc.
                    query = query_obj
            else:
                raise ValueError("Query is not valid Mongo format")
        else:
            # For SQL query, just return the raw string
            query = query_str
    except Exception as e:
        raise ValueError(f"Error parsing query: {e}")
    
    return query, datasets_list
        
# --- Execute SQL query ---
def execute_mysql_query(query):
    connection = pymysql.connect(
        host="ec2-18-225-255-15.us-east-2.compute.amazonaws.com",  # public IP or hostname
        user="root",
        password="Dsci351",
        database="transactions_db",
        port=3306
    )

    with connection.cursor() as cursor:
        cursor.execute(query)
        if query.strip().lower().startswith("select"):
            result = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            return pd.DataFrame(result, columns=column_names)
        else:
            connection.commit()
            return f"Query executed successfully: `{query.split()[0].upper()}`"

# --- Execute MongoDB query ---
def execute_mongo_query(query, datasets_list):
    mongo_uri = "mongodb://ec2-18-225-255-15.us-east-2.compute.amazonaws.com:27017"
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client["ecommerce"]
        #collection = db[collection_name.replace("_json", "")]

        collections = {
                "customers_json": db["customers_json"],
                "products_json": db["products_json"],
                "ratings_json": db["ratings_json"]
        }

        active_collection = collections[datasets_list[0]]

        if isinstance(query, dict):
            if "insertOne" in query:
                result = active_collection.insert_one(query["insertOne"])
                return f"Inserted ID: {result.inserted_id}"

            elif "insertMany" in query:
                result = active_collection.insert_many(query["insertMany"])
                return f"Inserted IDs: {result.inserted_ids}"

            elif "updateOne" in query:
                result = active_collection.update_one(
                    query["updateOne"]["filter"], query["updateOne"]["update"]
                )
                return f"Matched: {result.matched_count}, Modified: {result.modified_count}"

            elif "updateMany" in query:
                result = active_collection.update_many(
                    query["updateMany"]["filter"], query["updateMany"]["update"]
                )
                return f"Matched: {result.matched_count}, Modified: {result.modified_count}"

            elif "deleteOne" in query:
                result = active_collection.delete_one(query["deleteOne"])
                return f"Deleted Count: {result.deleted_count}"

            elif "filter" in query:
                result = list(active_collection.find(query["filter"], query.get("projection")).limit(5))
                df = pd.DataFrame(result)
                return df.head()

            else:
                print("Unrecognized operation:", query)

        elif isinstance(query, list):  # aggregation
            result = list(active_collection.aggregate(query))
            df = pd.DataFrame(result)
            return df.head()

    except Exception as e:
        return f"MongoDB Execution Error: {e}"

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
            result = execute_mongo_query(query, datasets_used)
        else:
            result = "Error: Cannot mix SQL (_df) and MongoDB (_json) datasets in a single query."

        if isinstance(result, pd.DataFrame):
            st.dataframe(result)
        else:
            st.write(result)

