from django.core.management.base import BaseCommand
from syllabus.models import Ques  # replace with actual app name
import html2text
import csv
from django.utils.timezone import localtime

class Command(BaseCommand):
    help = 'Export Ques model data to CSV with q_markdown field'

    def handle(self, *args, **kwargs):
        converter = html2text.HTML2Text()
        converter.ignore_links = False

        output_file = 'ques_export.csv'
        fields = [
            'q_no', 'q_statement', 'q_markdown', 'a', 'b', 'c', 'd',
            'correct_option', 'explanation', 'exam', 'year',
            'subject_name', 'section_name', 'topic_name', 'subtopic_name', 'microtopic_name',
            'unit', 'is_check', 'for_review', 'added_at', 'updated_at'
        ]

        with open(output_file, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()

            for q in Ques.objects.all():
                q_markdown = converter.handle(q.q_statement or "")
                writer.writerow({
                    'q_no': q.q_no,
                    'q_statement': q.q_statement,
                    'q_markdown': q_markdown.strip(),
                    'a': q.a,
                    'b': q.b,
                    'c': q.c,
                    'd': q.d,
                    'correct_option': q.correct_option,
                    'explanation': q.explanation,
                    'exam': q.exam,
                    'year': q.year,
                    'subject_name': q.subject_name,
                    'section_name': q.section_name,
                    'topic_name': q.topic_name,
                    'subtopic_name': q.subtopic_name,
                    'microtopic_name': q.microtopic_name,
                    'unit': q.unit,
                    'is_check': q.is_check,
                    'for_review': q.for_review,
                    'added_at': localtime(q.added_at).isoformat(),
                    'updated_at': localtime(q.updated_at).isoformat(),
                })

        self.stdout.write(self.style.SUCCESS(f"✅ Exported Ques data to {output_file}"))
