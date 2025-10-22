import openai
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the API key from the environment
api_key = os.getenv("OPENAI_API_KEY")

# Initialize the client
client = openai.OpenAI(api_key=api_key)

# Make request
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "What is this API calling in OpenAI? Give me a brief description of the API and its usage."}
    ],
    temperature=0.7
)

print(response.choices[0].message.content)