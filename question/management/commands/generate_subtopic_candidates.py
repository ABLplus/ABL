from django.core.management.base import BaseCommand
from django.db import transaction

import json
from typing import List
from pydantic import BaseModel

from syllabus.models import Topic, SubTopicCandidate
from question.models import Question

from openai import OpenAI


EXAMS_ALLOWED = ["CSE Prelims", "CDS", "CAPF"]


# =========================
# Structured Output Schemas
# =========================

class SubtopicItem(BaseModel):
    sequence: int
    name: str
    description: str
    demand: str
    question_ids: List[int]


class SubtopicCandidateOutput(BaseModel):
    subtopics: List[SubtopicItem]


# =========================
# Management Command
# =========================

class Command(BaseCommand):
    help = "Generate SubTopicCandidates using Structured Outputs (responses.parse)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic-id",
            type=int,
            default=131,
            help="Topic ID for which subtopics should be generated",
        )
        parser.add_argument(
            "--max-questions",
            type=int,
            default=210,
            help="Maximum number of questions to send to LLM",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing SubTopicCandidates before saving",
        )

    def handle(self, *args, **options):
        topic_id = options["topic_id"]
        max_q = options["max_questions"]
        replace = options["replace"]

        # -------------------------
        # Fetch Topic & Questions
        # -------------------------
        try:
            topic = Topic.objects.get(id=topic_id)
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Topic {topic_id} not found"))
            return

        questions = list(
            Question.objects
            .filter(topic=topic, exam_name__in=EXAMS_ALLOWED)
            .order_by("-year", "id")[:max_q]
        )

        if not questions:
            self.stdout.write(self.style.WARNING("No questions found. Aborting."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {len(questions)} questions for topic '{topic.name}'"
            )
        )

        # -------------------------
        # Prepare LLM Payload
        # -------------------------
        payload = [
            {
                "id": q.id,
                "exam": q.exam_name,
                "year": q.year,
                "question": (q.q_markdown or "").strip(),
                "options": {
                    "A": q.option_a,
                    "B": q.option_b,
                    "C": q.option_c,
                    "D": q.option_d,
                },
            }
            for q in questions
        ]

        # -------------------------
        # Call LLM (STRUCTURED)
        # -------------------------
        client = OpenAI()

        try:
            response = client.responses.parse(
                model="gpt-4o-mini",
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert UPSC exam analyst. "
                            "Your task is to cluster MCQs into syllabus-aligned subtopics "
                            "based strictly on conceptual and demand similarity."
                        ),
                    },
                    {
                        "role": "user",
                        "content": self.build_prompt(topic.name, payload),
                    },
                ],
                text_format=SubtopicCandidateOutput,
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"LLM call failed: {e}"))
            return

        # -------------------------
        # Extract Parsed Output
        # -------------------------
        parsed: SubtopicCandidateOutput = response.output_parsed

        if not parsed or not parsed.subtopics:
            self.stdout.write(self.style.ERROR("No subtopics returned by LLM"))
            return

        # -------------------------
        # Persist to DB
        # -------------------------
        with transaction.atomic():
            if replace:
                SubTopicCandidate.objects.filter(topic=topic).delete()

            for item in parsed.subtopics:
                SubTopicCandidate.objects.create(
                    topic=topic,
                    name=item.name,
                    description=item.description,
                    demand=item.demand,
                    sequence_number=item.sequence,
                    question_ids=item.question_ids,
                    status=SubTopicCandidate.Status.PENDING,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {len(parsed.subtopics)} SubTopicCandidates for topic '{topic.name}'"
            )
        )

    # -------------------------
    # Prompt Builder
    # -------------------------
    def build_prompt(self, topic_name: str, questions: list) -> str:
        return f"""
You are given multiple-choice questions (MCQs) from competitive exams
belonging to the topic:

TOPIC: "{topic_name}"

TASK:
• Infer an OPTIMUM number of subtopics based on conceptual and demand diversity.
• Prefer merging over over-splitting.
• Typical range: 3–10subtopics (adjust only if clearly justified).

RULES:
• Every question must belong to EXACTLY ONE subtopic.
• Use the FULL MCQ (question + options).
• Subtopic names must be syllabus-aligned and precise.
• Do not invent concepts not present in the questions.

Return ONLY structured output.

QUESTIONS:
{json.dumps(questions, indent=2)}
"""
