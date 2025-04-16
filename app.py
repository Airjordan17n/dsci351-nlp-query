# app.py

import streamlit as st
import openai
import os
import pymongo
import mysql.connector

# Load API key securely
openai.api_key = os.getenv("OPENAI_API_KEY")

st.title("Natural Language → Database Query Interface")

# User Input
user_input = st.text_area("Enter your natural language query:")
db_choice = st.selectbox("Choose a database:", ["MySQL", "MongoDB"])

def generate_query(nl_query, db_type):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": f"You are an expert at converting natural language into {db_type} queries."},
            {"role": "user", "content": nl_query}
        ]
    )
    return response['choices'][0]['message']['content']

def execute_mysql_query(query):
    try:
        conn = mysql.connector.connect(
            host="your_mysql_host",
            user="your_mysql_user",
            password="your_mysql_password",
            database="your_mysql_db"
        )
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    except Exception as e:
        return f"MySQL Error: {e}"

def execute_mongo_query(query):
    try:
        client = pymongo.MongoClient("your_mongo_uri")
        db = client["your_mongo_db"]
        collection = db["your_collection"]
        result = eval(f"collection.{query}")
        return list(result)
    except Exception as e:
        return f"MongoDB Error: {e}"

# When user clicks submit
if st.button("Submit"):
    if not user_input.strip():
        st.warning("Please enter a query first.")
    else:
        st.subheader("Generated Query")
        query = generate_query(user_input, db_choice)
        st.code(query, language="sql" if db_choice == "MySQL" else "python")

        st.subheader("Query Results")
        if db_choice == "MySQL":
            results = execute_mysql_query(query)
        else:
            results = execute_mongo_query(query)

        st.write(results)
