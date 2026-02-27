import openai
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_fund_manager_info(fund_house, scheme_name):
    client_search = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = client_search.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[
            {
                "role": "user",
                "content": f"""Find information about the fund manager of {scheme_name} from {fund_house} in India.
                
                Return the following in a clean structured format:
                - Fund Manager Name
                - Experience (years)
                - Educational Background
                - Other funds they manage
                - Investment philosophy or style in 2-3 sentences
                - Any recent commentary or views
                
                If you cannot find specific information, say so clearly. Do not make up information.
                Do not include source URLs or citations in your response.
                Format the output cleanly without any markdown symbols like ** or *.
                Write in a professional but conversational tone."""
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