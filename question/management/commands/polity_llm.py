from django.core.management.base import BaseCommand
from question.models import Question, OLT as OLTModel
from syllabus.models import Subject, Section, Topic
from openai import OpenAI
import json, time, os
from dotenv import load_dotenv
from json.decoder import JSONDecodeError

# Load environment variables
dotenv_path = os.getenv('DOTENV_PATH', None)
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()

# Import syllabus tree and OLT types
from utils.polity_tree import TREE
from utils.olt_types import OLT_TYPE_JSON

class Command(BaseCommand):
    help = """
    Tag CSE Prelims Polity and Governance questions with:
      - exact section & topic names (from TREE)
      - OLT code & OLT FK if it exists
      - markdown explanation in explanation_generated
    If section/topic don't match DB, skip FK but still save names and explanation.
    """

    def handle(self, *args, **kwargs):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.stderr.write("OPENAI_API_KEY not set in environment.")
            return

        client = OpenAI(api_key=api_key)

        # Fetch the Subject FK
        try:
            subject_obj = Subject.objects.get(name="Polity and Governance")
        except Subject.DoesNotExist:
            self.stderr.write("Subject 'Polity and Governance' not found.")
            return

        # Select questions needing tags
        questions = Question.objects.filter(
            exam_name="CSE Prelims",
            subject__isnull=True,
            subject_name="Polity and Governance"
        )

        for i, q in enumerate(questions, start=1):
            self.stdout.write(f"[{i}] Processing Question ID {q.id}")

            # Assign Subject FK if not already set
            q.subject = subject_obj
            q.save(update_fields=["subject"])

                        # Prepare prompts
            sections = list(TREE.keys())
            section_list = ", ".join(sections)
            system_prompt = f"""
You are an expert at UPSC MCQ tagging and explanation.

Hierarchy:
- Sections available: {section_list}
- For each Section, the Topics are:
{json.dumps(TREE, indent=4)}

Tasks:
1. Choose exactly one Section from the above list.
2. Choose exactly one Topic from the chosen Section's topics.
3. Choose the correct OLT code from this schema:
{json.dumps(OLT_TYPE_JSON)}
4. Generate a markdown-formatted explanation for the correct option ({q.correct_option}):
   - Heading: 'Correct Option'
   - Heading: 'Why this is correct'
   - Heading: 'Why others are incorrect'
   - Use bullet points under each.

Return only valid JSON with keys:
{{
  "section_name": "<Exact section>"
  "topic_name":   "<Exact topic under that section>"
  "olt_type":     "<OLT code>"
  "explanation_markdown": "<Markdown text>"
}}
""".strip()

            user_prompt = f"""
MCQ:
Q: {q.q_markdown}
A) {q.option_a}
B) {q.option_b}
C) {q.option_c}
D) {q.option_d}
Correct Option: {q.correct_option}
""".strip()

            # Call LLM
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role":"system","content":system_prompt},
                        {"role":"user","content":user_prompt}
                    ],
                    temperature=0.3
                )
                raw = resp.choices[0].message.content.strip()
                data_str = raw[raw.find('{'):raw.rfind('}')+1]
                result = json.loads(data_str)
            except JSONDecodeError as je:
                self.stderr.write(f"❌ JSON decode error for Q {q.id}: {je}")
                self.stderr.write(f"Raw: {raw}")
                continue
            except Exception as e:
                self.stderr.write(f"❌ LLM error for Q {q.id}: {e}")
                continue

            # Unpack LLM output
            section_name = result.get('section_name')
            topic_name   = result.get('topic_name')
            olt_code     = result.get('olt_type')
            explanation  = result.get('explanation_markdown')

            # Always save names and explanation
            q.section_name = section_name
            q.topic_name   = topic_name
            q.olt_type     = olt_code
            q.explanation_generated = explanation

            # Attempt to assign Section FK
            try:
                sec_obj = Section.objects.get(name=section_name, subject=subject_obj)
                q.section = sec_obj
            except Section.DoesNotExist:
                self.stderr.write(f"⚠️ Section '{section_name}' not found for Q {q.id}, skipping FK.")

            # Attempt to assign Topic FK
            try:
                if q.section:
                    top_obj = Topic.objects.get(name=topic_name, section=q.section)
                else:
                    top_obj = Topic.objects.get(name=topic_name)
                q.topic = top_obj
            except Topic.DoesNotExist:
                self.stderr.write(f"⚠️ Topic '{topic_name}' not found for Q {q.id}, skipping FK.")

            # Attempt to assign OLT FK
            try:
                olt_obj = OLTModel.objects.get(code=olt_code)
                q.olt = olt_obj
            except OLTModel.DoesNotExist:
                self.stderr.write(f"⚠️ OLT code '{olt_code}' not found for Q {q.id}, skipping FK.")

            # Save updated fields
            q.save(update_fields=[
                'section_name','topic_name','olt_type','explanation_generated',
                'section','topic','olt'
            ])
            self.stdout.write(self.style.SUCCESS(f"✅ Question {q.id} saved."))

            time.sleep(1)
