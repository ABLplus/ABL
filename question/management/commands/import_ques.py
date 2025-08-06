# question/management/commands/import_ques.py

from django.core.management.base import BaseCommand
from django.db import transaction

from syllabus.models import Ques
from question.models import Question

class Command(BaseCommand):
    help = "Bulk-import all Ques (with topic) into the Question model"

    def handle(self, *args, **options):
        qs = Ques.objects.filter(topic__isnull=False)
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("✔ No Ques entries with a topic to import."))
            return

        self.stdout.write(f"⏳ Preparing to import {total} Ques entries…")
        to_create = []

        # Pre-fetch related FKs to avoid N+1
        for q in qs.select_related(
            'subject', 'section', 'topic', 'subtopic', 'microtopic', 'olt'
        ):
            to_create.append(
                Question(
                    year                   = q.year,
                    exam_name              = q.exam,
                    question_html          = q.q_statement,
                    q_markdown             = q.q_markdown,
                    option_a               = q.a,
                    option_b               = q.b,
                    option_c               = q.c,
                    option_d               = q.d,
                    correct_option         = q.correct_option,
                    explanation_html       = q.explanation,
                    explanation_generated  = q.exp_generated,
                    unit                   = q.unit,
                    q_no                   = q.q_no,
                    subject_name           = q.subject_name,
                    section_name           = q.section_name,
                    topic_name             = q.topic_name,
                    subtopic_name          = q.subtopic_name,
                    microtopic_name        = q.microtopic_name,
                    subject                = q.subject,
                    section                = q.section,
                    topic                  = q.topic,
                    subtopic               = q.subtopic,
                    olt_type               = q.olt_type,
                    olt                    = q.olt,
                )
            )

        # Bulk-create in a single transaction, in batches of 500
        with transaction.atomic():
            Question.objects.bulk_create(to_create, batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"✅ Bulk-imported {len(to_create)} questions."))
