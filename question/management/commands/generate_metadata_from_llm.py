from django.core.management.base import BaseCommand
from syllabus.models import Ques
from django.conf import settings
from openai import OpenAI
import json
import time
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# ✅ Import syllabus tree and OLT types
from utils.olt_types import OLT_TYPE_JSON
from utils.culture_tree import TREE


class Command(BaseCommand):
    help = "Generate metadata (syllabus tags, OLT type, explanation) using LLM for Ques with unit=1"

    def handle(self, *args, **kwargs):
        api_key = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        questions = Ques.objects.filter(unit=8, subject__name="Art and Culture")

        for i, q in enumerate(questions, 1):
            print(f"\n[{i}] Processing Ques ID {q.id}")

            system_prompt = f"""
You are an expert at UPSC MCQ tagging and explanation.

Your task:
1. Assign the most appropriate section and topic based on this syllabus tree:
{json.dumps(TREE)}

2. Identify the Option Layout Type (OLT) based on this schema:
{json.dumps(OLT_TYPE_JSON)}

3. "olt_type" output shold be one of the keys from OLT_TYPE_JSON i.e. the OLT code such as OLT-01,OLT-02 etc.

3. Clearly explain why the correct option is correct. And why the other options are incorrect.

4.Be brief, accurate, and use only information relevant to the question. preference 150 words and Maximum 300 words.Don't repeat the full question or options. Just focus on reasoning and clarity. If deem fit, at last provide a concept note for the main topic of the question in additional 100 words.

5. Give the explanation in markdown format.Include line breaks. Include headings for Correct option, why correct, and why others incorrect. Use bullet points for clarity.


Return a valid JSON:
{{
  "section_name": "...",
  "topic_name": "...",
  "olt_type": "...",
  "updated_explanation": "..."
}}
""".strip()

            user_prompt = f"""
MCQ:
Q: {q.q_statement}
A. {q.a}
B. {q.b}
C. {q.c}
D. {q.d}

Correct Option: {q.correct_option}
""".strip()

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3
                )

                content = response.choices[0].message.content
                result = json.loads(content)

                # Save result to DB
                q.section_name = result.get('section_name')
                q.topic_name = result.get('topic_name')
                # q.subtopic_name = result.get('subtopic_name')
                q.olt_type = result.get('olt_type')
                q.exp_generated = result.get('updated_explanation')
                q.save()

                print(f"✅ Ques {q.id} saved.")
                time.sleep(1)

            except Exception as e:
                print(f"❌ Error for Ques {q.id}: {e}")
                continue
