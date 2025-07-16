import openai
import os
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def call_gpt_explanation(data):
    question_text = f"""
Question:
{data['q_markdown']}

Options:
A. {data['a']}
B. {data['b']}
C. {data['c']}
D. {data['d']}

Correct Option: {data['correct_option']}
"""

    system_prompt = (
        "You are a UPSC Polity expert. Your job is to clearly explain why the correct option is correct. And why the other options are incorrect."
        "Be brief, accurate, and use only information relevant to the question. preference 150 words and Maximum 300 words." 
        "Don't repeat the full question or options. Just focus on reasoning and clarity." "Give the explanation in markdown format." "Include line breaks. Include headings for Correct option, why correct, and why others incorrect. Use bullet points for clarity." 
    )

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question_text}
            ],
            temperature=0.4
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Error generating explanation: {str(e)}"
