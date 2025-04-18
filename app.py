import streamlit as st
import pandas as pd
import openai
import pymysql
from sshtunnel import SSHTunnelForwarder
import os

# --- Set API Key from secrets ---
openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- OPTIONAL: Reconstruct PEM file from secrets (if using Streamlit secrets instead of uploaded file) ---
# with open("dsci351.pem", "w") as f:
#     f.write(st.secrets["EC2_PEM"])
# os.chmod("dsci351.pem", 0o600)

# --- Load Datasets from /data ---
try:
    cards_df = pd.read_csv("data/cards_data.csv", nrows=1000)
    users_df = pd.read_csv("data/users_data.csv", nrows=1000)
except FileNotFoundError as e:
    st.error(f"Could not load dataset: {e}")
    st.stop()

cards_df_columns = list(cards_df.columns)
users_df_columns = list(users_df.columns)

# --- Dataset Schema Map ---
dataset_fields_map = {
    "users_df": users_df_columns,
    "cards_df": cards_df_columns
}

# --- Determine relevant datasets for the user's question ---
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

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()

# --- Generate SQL query ---
def create_query(user_input):
    datasets = which_dataset(user_input, dataset_fields_map)
    datasets_list = [d.strip() for d in datasets.split(",")]

    columns_dict = {d: dataset_fields_map[d] for d in datasets_list}
    schema_description = "\n".join([f"{k}: {', '.join(v)}" for k, v in columns_dict.items()])

    prompt = f"""
You are an expert SQL query writer.

Here are the tables and their fields:
{schema_description}

The user asked:
\"{user_input}\"

Return ONLY a valid MySQL query using SQL syntax — no explanation.
"""

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )

    raw_response = response.choices[0].message.content.strip()
    return raw_response, datasets_list

# --- Execute SQL query via SSH tunnel to EC2 ---
def execute_mysql_query(query):
    ssh_host = 'ec2-3-144-6-200.us-east-2.compute.amazonaws.com'
    ssh_user = 'ubuntu'
    ssh_key = 'dsci351.pem'  # This key must exist in root directory or be built from secrets

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
            connection = pymysql.connect(
                host=mysql_host,
                user=mysql_user,
                password=mysql_password,
                database=mysql_db,
                port=tunnel.local_bind_port
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
    except Exception as e:
        return f"MySQL Execution Error: {e}"

# --- Streamlit App Layout ---
st.set_page_config(page_title="Natural Language DB Query", layout="wide")
st.title("Natural Language → SQL Query Interface")

st.markdown("Try queries like:")
st.markdown("- *Get users born in 1999*")
st.markdown("- *Insert a new user with ID 9000 and name John Doe*")
st.markdown("- *List all cards with limit over 5000*")

user_input = st.text_area("Enter your natural language query:")

if st.button("Generate and Run Query"):
    if not user_input.strip():
        st.warning("Please enter a query.")
    else:
        st.subheader("Generated SQL Query")
        query, datasets_used = create_query(user_input)
        st.code(query, language="sql")

        st.subheader("Query Results")
        results = execute_mysql_query(query)
        if isinstance(results, pd.DataFrame):
            st.dataframe(results)
        else:
            st.success(results)
