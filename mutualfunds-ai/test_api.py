import openai
import requests
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file


client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Test the mutual fund API
response = requests.get("https://api.mfapi.in/mf/100033")

response_2 = response.json()
print("Fund House: ", response_2["meta"]["fund_house"])
print("Scheme Name: ", response_2["meta"]["scheme_name"])

# Test the OpenAI API

prompt = f"Summarize the current mutual fund to a first time investor in simple terms :  {response_2['meta']}"
completions = client.chat.completions.create(
    model="gpt-4o",
    messages=[
       
        {"role": "user", "content": prompt}
    ]
)

print("This is the AI summary \n")
print(completions.choices[0].message.content)




