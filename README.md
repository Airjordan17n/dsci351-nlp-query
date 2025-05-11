**Natural Language to SQL/MongoDB Converter**
This project converts natural language queries into MySQL or MongoDB queries using a language model (OpenAI GPT-3.5 Turbo) and executes them on sample databases. A Streamlit frontend allows users to input queries and view results.

**Prerequisites**
All required libraries are listed in requirements.txt.

**Software & Tools**
- Python 3
- AWS EC2 instance (for hosting)
- Streamlit
- OpenAI API (GPT-3.5 Turbo)
- SSH access using sshtunnel
- MongoDB and MySQL installed on EC2
- pymysql and pymongo installed on EC2
- .pem key for AWS EC2 access

**API Key**
You need an OpenAI API key.
Option 1: Replace this part in line #13 with your API Key:
st.secrets["OPENAI_API_KEY"]

Option 2: Upload it manually in the Streamlit Secrets tab online.

**Running the Code on AWS EC2**
Security Group Setup
Go to your EC2 Security Group settings.

Add the following inbound rules:
- MySQL/Aurora: TCP Port 3306, Source: 0.0.0.0/0
- Custom TCP: TCP Port 27017, Source: 0.0.0.0/0
- SSH: TCP Port 22, Source: 0.0.0.0/0

Update Bind IP
- On your EC2 instance, make sure both MySQL and MongoDB have their bind IP set to 0.0.0.0 in their respective config files.

**Upload & Configure Dataset**
1. Upload your data to EC2.
2. Rename tables and databases to match the dataset_field_map in the GitHub repo.
3. Edit EC2 Connection Credentials
4. In the code, go to lines 168–197.
    Replace these with your EC2 IP, username, password, port, and DB names.

**Initial SSH Tunnel Workaround**

First run:
1. Uncomment lines 169–190 (SSH tunnel setup)
2. Comment out lines 191–197
3. Run the code (expect an error).

Second run:
1. Comment out lines 169–190
2. Uncomment lines 191–197
3. Push to GitHub and re-run.

**How to Use (Streamlit Inputs)**
- Start your EC2 instance and ensure both MySQL and MongoDB are running.
- Go to the Streamlit UI.
- Type a prompt (e.g., Find names of products that have a unit price less than 3).
- Click Submit to generate and run the query.

**Known Issues**
- SSH tunneling with Streamlit may require a manual workaround (see above).
- Model outputs can sometimes require post-processing. If the site errors, try refreshing and resubmitting.
