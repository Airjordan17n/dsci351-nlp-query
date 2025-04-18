!pip install openai
!pip install pymysql
!pip install pymongo[srv]
!pip install sshtunnel

import pandas as pd
import openai
import json
import getpass
import pymysql
from pymongo import MongoClient
from sshtunnel import SSHTunnelForwarder

api_key = getpass.getpass("Enter your OpenAI API key: ")
client = openai.OpenAI(api_key=api_key)

def which_dataset(user_input, dataset_fields):
  schema_description = "\n".join([
    f"{name}: {' ,'.join(fields)}" for name, fields in dataset_fields.items()
    ])

  prompt = f"""
  You are an expert data scientist.

  Here are the available datasets and the fields they contain:
  {schema_description}

  The user asked:
  \"{user_input}\"

  Based on the fields and the question, which dataset(s) are needed to answer this question?
  In most cases, only one dataset is needed. However, in some cases, a join function is needed and so two or more data sets will be required.
  Respond ONLY with the dataset name(s) – "cards_df", "transactions_df", or "users_df" – seperated by a comma. No explanation.
  """

  response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
      {"role": "user", "content": prompt}
      ])

  datasets = response.choices[0].message.content
  return datasets



def create_query(user_input):
  datasets = which_dataset(user_input, dataset_fields_map)
  datasets_list = datasets.split(", ")

  # Ensure only datasets of the same type (CSV with CSV, JSON with JSON) are selected
  csv_datasets = ["cards_df", "transactions_df", "users_df"]
  json_datasets = ["customers_json", "products_json", "ratings_json"]

    # Separate CSV and JSON datasets
  selected_csv_datasets = [dataset for dataset in datasets_list if dataset in csv_datasets]
  selected_json_datasets = [dataset for dataset in datasets_list if dataset in json_datasets]

    # If both types of datasets (CSV and JSON) are mixed, raise an error
  if selected_csv_datasets and selected_json_datasets:
      raise ValueError("Cannot mix CSV (MySQL) and JSON (MongoDB) datasets. Please ensure only one type is selected.")


  # make a dictionary containing the datasets we are using and their columns
  columns_dict = {}
  for dataset in dataset_fields_map:
    if dataset in datasets_list:
      columns_dict[dataset] = dataset_fields_map[dataset]

  # make a schema description ONLY for the datasets we are using
  schema_description = "\n".join([
    f"{name}: {' ,'.join(fields)}" for name, fields in columns_dict.items()
    ])

  # Check if the datasets are NoSQL (JSON) or SQL (CSV)
  is_nosql = any(dataset in ["customers_json", "products_json", "ratings_json"] for dataset in datasets_list)

  # Based on the dataset type, create the right query prompt
  if is_nosql:
      prompt = f"""
      You are an expert MongoDB query writer.
      Here are the datasets we are using and the fields they contain:
      {schema_description}

      The user asked:
      \"{user_input}\"

      Return ONLY the MongoDB query (in JSON format) that responds to what the user asked.
      """
  else:
      prompt = f"""
      You are an expert data scientist.
      Here are the datasets we are using and the fields they contain:
      {schema_description}

      The user asked:
      \"{user_input}\"

      Return ONLY the SQL query that responds to what the user asked.
      """

  # return the query that the openAI API gave us
  response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
      {"role": "user", "content": prompt}
        ])

  query = response.choices[0].message.content
  return query
