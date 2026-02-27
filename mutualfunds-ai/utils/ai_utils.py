import openai
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_fund_manager_and_holdings(fund_house, scheme_name):
    response = client.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[
            {
                "role": "user",
                "content": f"""Find the following information about {scheme_name} from {fund_house} in India.

FUND MANAGER:
- Name and years of experience
- Educational background  
- Other funds they manage
- Investment philosophy in 2-3 sentences

PORTFOLIO HOLDINGS:
- Top 10 stock holdings with approximate percentage allocation
- Top 3-4 sector allocations with percentages
- Any notable recent changes to the portfolio

Format each section clearly under the headers FUND MANAGER and PORTFOLIO HOLDINGS.
Do not include source URLs or citations.
Write in plain professional English.
If specific information is not available say so clearly, do not make up data.
Important: Do not include any source citations, URLs, or references like (__moneycontrol.com__) anywhere in your response.
Do not use bullet points or asterisks. Write in clean plain text with line breaks between sections."""
            }
        ]
    )
    return response.choices[0].message.content


def get_ai_summary(meta, returns):

    
    prompt = f"""You are a financial advisor explaining mutual funds to a first time investor in India

    FUND_NAME = {meta["scheme_name"]}
    FUND_HOUSE = {meta["fund_house"]}
    CATEGORY = {meta["scheme_category"]}
    RETURNS = {returns}

    Write a 4 sentence plain english summary covering
    1) What this fund does
    2) Who is it suitable for
    3) How it has performed
    4) One thing to be aware of when investing in this fund

    No bullet points, no jargons, Conversational tone.

    """
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content


def build_fund_system_prompt(meta, nav_data, returns, manager_info):
    current_nav = nav_data[0]["nav"]
    oldest_date = nav_data[-1]["date"]
    
    # Find COVID performance
    covid_crash = None
    covid_recovery = None
    for entry in nav_data:
        if entry["date"] == "23-03-2020" or entry["date"] == "24-03-2020":
            covid_crash = entry["nav"]
        if entry["date"] == "01-01-2021":
            covid_recovery = entry["nav"]
    
    prompt = f"""
You are an expert mutual fund analyst assistant. You have deep knowledge about the following specific fund and your job is to answer any questions the user has about it clearly, honestly, and in plain English.

FUND DETAILS:
- Name: {meta['scheme_name']}
- Fund House: {meta['fund_house']}
- Category: {meta['scheme_category']}
- Current NAV: ₹{current_nav}
- Fund history since: {oldest_date}

RETURNS:
- 1 Year: {returns.get('1 Year', 'N/A')}%
- 3 Year: {returns.get('3 Year', 'N/A')}%
- 5 Year: {returns.get('5 Year', 'N/A')}%
- 10 Year: {returns.get('10 Year', 'N/A')}%

COVID PERFORMANCE:
- NAV at crash (March 2020): ₹{covid_crash if covid_crash else 'Not available'}
- NAV at recovery (Jan 2021): ₹{covid_recovery if covid_recovery else 'Not available'}

FUND MANAGER AND PORTFOLIO HOLDINGS:
{manager_info}

YOUR BEHAVIOUR:
- Answer only questions related to this fund or mutual funds in general
- Be conversational, clear, and avoid jargon
- If you don't know something specific, say so honestly
- Never make up numbers or facts not present above
- Keep answers concise — 3-5 sentences unless the question needs more detail
- If asked for investment advice, share analysis but remind the user to consult a financial advisor
"""
    return prompt

def chat_with_fund(messages):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )
    return completion.choices[0].message.content