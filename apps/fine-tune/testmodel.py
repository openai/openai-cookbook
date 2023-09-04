
import os
from dotenv import load_dotenv

import openai
import requests 



load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ORG_ID = os.getenv("ORG_ID")


openai.organization = ORG_ID
openai.api_key = OPENAI_API_KEY
# print(openai.Model.list())



headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}"
}

params = {
    "limit": 2
}

response = requests.get("https://api.openai.com/v1/fine_tuning/jobs", headers=headers, params=params)

# Check the status and print the response
if response.status_code == 200:
    print(response.json())
else:
    print(f"Failed to get data: {response.content}")