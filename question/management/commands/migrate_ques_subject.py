# File: question/management/commands/migrate_ques_subject.py

from django.core.management.base import BaseCommand
from django.db.models import Q
from syllabus.models import Ques, Subject
from question.models import Question, OLT

class Command(BaseCommand):
    help = (
        "Copy Ques from syllabus to question app for "
        "Subject.name='Polity and Governance', excluding CSE Prelims post-1999"
    )

    def handle(self, *args, **kwargs):
        subject_name = "Polity and Governance"
        source_subject = Subject.objects.filter(name=subject_name).first()

        if not source_subject:
            self.stdout.write(self.style.ERROR(
                f"❌ Subject '{subject_name}' not found in syllabus."
            ))
            return

        # Base queryset: only this subject
        qs = Ques.objects.filter(subject=source_subject)
        # Exclude any Ques where exam='CSE Prelims' AND year > 1999
        qs = qs.exclude(Q(exam__iexact="CSE Prelims") & Q(year__gt=1999))

        total = qs.count()
        copied = 0
        unmatched_olt = []

        for q in qs:
            # 1) Match OLT by code, then by name
            olt_obj = None
            if q.olt_type:
                olt_obj = OLT.objects.filter(code=q.olt_type).first()
                if not olt_obj:
                    olt_obj = OLT.objects.filter(
                        name__iexact=q.olt_type.strip()
                    ).first()
                if not olt_obj:
                    unmatched_olt.append((q.q_no, q.year, q.exam, q.olt_type))
                    self.stdout.write(self.style.WARNING(
                        f"⚠️ OLT not found for '{q.olt_type}' in "
                        f"Q{q.q_no} ({q.year} - {q.exam})"
                    ))

            # 2) Create the Question record
            Question.objects.create(
                source_type='PYQ',
                year=q.year,
                exam_name=q.exam,
                question_html=q.q_statement,
                q_markdown=q.q_markdown,
                option_a=q.a,
                option_b=q.b,
                option_c=q.c,
                option_d=q.d,
                correct_option=q.correct_option,
                explanation_html=q.explanation,
                explanation_generated=q.exp_generated,
                unit=q.unit,
                subject_name=q.subject_name,
                section_name=q.section_name,
                topic_name=q.topic_name,
                subtopic_name=q.subtopic_name,
                microtopic_name=q.microtopic_name,
                subject=q.subject,
                section=q.section,
                topic=q.topic,
                subtopic=q.subtopic,
                olt_type=q.olt_type,
                olt=olt_obj
            )
            copied += 1

        # Summary output
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Migrated {copied} out of {total} questions "
            f"for subject '{subject_name}', excluding CSE Prelims post-1999."
        ))

        if unmatched_olt:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️ {len(unmatched_olt)} questions had unmatched OLT types:"
            ))
            for q_no, year, exam, olt_type in unmatched_olt:
                self.stdout.write(
                    f"  - Q{q_no} ({year} - {exam}) → OLT: '{olt_type}'"
                )
