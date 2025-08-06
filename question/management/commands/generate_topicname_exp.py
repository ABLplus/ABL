# file: question/management/commands/generate_topics_and_explanations.py
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from question.models import Question  # adjust if your model is named differently
from openai import OpenAI


class Command(BaseCommand):
    help = "Generate topic_name (general UPSC) and explanation_generated for Questions with NULL topic FK"

    def handle(self, *args, **kwargs):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.stderr.write(self.style.ERROR("OPENAI_API_KEY not set"))
            return

        client = OpenAI(api_key=api_key)

        questions = Question.objects.filter(topic__isnull=True).order_by("id")
        if not questions.exists():
            self.stdout.write(self.style.WARNING("No questions with NULL topic found."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Processing {questions.count()} question(s)..."))

        system_prompt = """
You are an expert at UPSC MCQ tagging and explanation.

Tasks:
1) Assign the MOST appropriate UPSC syllabus topic name for the question (no tree provided).
   - Use concise, standard UPSC terms (e.g., "Indian Polity — Parliament", "Economy — Inflation",
     "Environment — Biodiversity", "History — Modern India", "Geography — Monsoons",
     "Science & Tech — Space", "International Relations — International Organizations",
     "Art & Culture — Architecture"). Return ONE best-fit topic_name string.

2) Write a concise, accurate explanation in markdown:
   - Headings: "Correct option", "Why correct", "Why others incorrect"
   - Use bullet points; ~150 words (max 300).
   - Do not repeat the full question or options.
   - Optionally end with a brief concept note (~100 words).

Return ONLY valid JSON:
{
  "topic_name": "...",
  "explanation_generated": "..."
}
""".strip()

        for i, q in enumerate(questions, start=1):
            self.stdout.write(f"[{i}] Question ID {q.id}")

            user_prompt = f"""
MCQ:
Q: {q.q_markdown}
A. {q.option_a}
B. {q.option_b}
C. {q.option_c}
D. {q.option_d}

Correct Option: {q.correct_option}
""".strip()

            try:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},  # enforce JSON-only
                )

                data = json.loads(resp.choices[0].message.content)
                topic_name = (data.get("topic_name") or "").strip()
                explanation_generated = (data.get("explanation_generated") or "").strip()
                if not topic_name:
                    raise ValueError("Missing 'topic_name' in model response")

                with transaction.atomic():
                    q.topic_name = topic_name
                    q.explanation_generated = explanation_generated  # rename to q.exp_generated if needed
                    q.save(update_fields=["topic_name", "explanation_generated"])

                self.stdout.write(self.style.SUCCESS(f"✅ Saved Question {q.id}"))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"❌ Error for Question {q.id}: {e}"))
                continue

        self.stdout.write(self.style.SUCCESS("Done."))
