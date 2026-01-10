from django.core.management.base import BaseCommand
from question.models import Question
from django.conf import settings
from openai import OpenAI
import json
import time
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()


class Command(BaseCommand):
    help = "Generate high-quality explanations for all Ques using LLM (stores Markdown in exp_generated)."

    def handle(self, *args, **kwargs):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.stdout.write(self.style.ERROR("OPENAI_API_KEY not set in environment."))
            return

        client = OpenAI(api_key=api_key)

        # 🔁 Change queryset if you want to restrict (e.g. only a unit/subject or only missing explanations)
        questions = Question.objects.all().order_by("id")
        total = questions.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("No questions found in Ques table."))
            return

        self.stdout.write(self.style.NOTICE(
            f"Starting explanation generation for {total} questions..."
        ))

        # --- System prompt: Explanation + Concept Note (knowledge) + Exam Demand separate ---
        system_prompt = """
You are an expert UPSC Prelims MCQ explainer.

Your ONLY task is to write a high-quality explanation for ONE MCQ.

You will be given:
- The question stem
- Four options (A, B, C, D)
- The correct option label (e.g., "A", "B", etc.)

Your goals:

1. Give a **brief, clear explanation** for why the correct option is right.
2. For **each wrong option only**, explain in 1–3 bullet points:
   - What that option actually refers to (correct factual context). Give the additional information needed to understand that option.
   - Why it does NOT satisfy the specific demand of this question.
   - If the option is partially true or related, mention that nuance briefly.
3. Provide a **Concept Note (Core Knowledge)**:
   - This is a concise note for information/knowledge content.
   - Summarise the key facts, definitions, relationships, and structure of the main concept(s) behind the question.
   - Think of it as a mini-note a student could revise to understand the topic itself, independent of the specific MCQ.
   - Length: about 80–150 words as per the complexity of the topic.


Very important constraints:

- DO NOT repeat the full question or options verbatim.
- You may restate key phrases briefly if needed to make the explanation clear.
- Keep the explanation factually accurate and UPSC-appropriate.
- Prefer total length around 250–400 words (excluding markdown syntax).

Output format: STRICT MARKDOWN, using this exact hierarchy and headings:

# Explanation for Question

## 1. Brief Answer Explanation

- Start with: **Correct Option: X – <short name/idea>**
- Then 3–6 bullet points explaining the core reasoning. Give core information needed to understand why this option is correct.  

## 2. Why Other Options Are Not Correct

- Create subsections ONLY for the incorrect options.
- Do NOT create a subsection for the correct option here.

### Option A

- 1–3 bullet points as described above (only if A is incorrect).
- If A is the correct option, SKIP creating this subsection.

### Option B

- Same pattern (only if incorrect).

### Option C

- Same pattern (only if incorrect).

### Option D

- Same pattern (only if incorrect).

## 3. Concept Note (Core Knowledge)

- One short paragraph (around 80–120 words).
- Focus ONLY on the information/knowledge content:
  - Key facts, definitions, classifications, relationships.
  - Enough for a student to revise the topic itself.


Return ONLY this markdown explanation. Do NOT return JSON.
""".strip()

        for i, q in enumerate(questions, 1):
            percent = (i / total) * 100
            self.stdout.write(
                f"\n[{i}/{total}] ({percent:.1f}%) Processing Ques ID {q.id}",
                ending=""
            )

            user_prompt = f"""
Generate a high-quality explanation for the following UPSC-style MCQ.

Question:
{q.q_markdown}

Options:
A. {q.option_a}
B. {q.option_b}
C. {q.option_c}
D. {q.option_d}

Correct Option: {q.correct_option}
""".strip()

            try:
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",  # or "gpt-4.1-mini" if you want cheaper runs
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )

                content = response.choices[0].message.content

                # Save explanation markdown into exp_generated (or explanation_html if you prefer)
                q.explanation_html = content
                q.save(update_fields=["explanation_html"])


                self.stdout.write(self.style.SUCCESS(" ✅ saved"))
                time.sleep(0.5)  # optional, to be gentle with rate limits

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" ❌ Error: {e}"))
                continue

        self.stdout.write(self.style.SUCCESS("\nAll done! Explanations generated for processed questions."))
