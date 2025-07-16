import csv
from django.core.management.base import BaseCommand
from syllabus.models import Ques
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = "Import Ques data from a CSV file (comma-separated)"

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        count = 0

        with open(csv_file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    ques = Ques(
                        q_no=row['q_no'],
                        q_statement=row['q_statement'],
                        q_markdown=row.get('q_markdown') or '',
                        a=row['a'],
                        b=row['b'],
                        c=row['c'],
                        d=row['d'],
                        correct_option=row['correct_option'],
                        explanation=row['explanation'],
                        exam=row['exam'],
                        year=int(row['year']) if row.get('year') else None,
                        unit=int(row['unit']) if row.get('unit') else None,
                        is_check=row['is_check'].strip().lower() == 'true',
                        for_review=row['for_review'].strip().lower() == 'true',
                        added_at=parse_datetime(row['added_at']) if row.get('added_at') else None,
                        updated_at=parse_datetime(row['updated_at']) if row.get('updated_at') else None,
                        subject_name=row.get('subject_name', None),
                        section_name=row.get('section_name', None),
                        topic_name=row.get('topic_name', None),
                        subtopic_name=row.get('subtopic_name', None),
                        microtopic_name=row.get('microtopic_name', None),
                        OLT=row.get('OLT', None),
                    )
                    ques.save()
                    count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"⚠️ Skipped row due to error: {e}"))

        self.stdout.write(self.style.SUCCESS(f"✅ Successfully imported {count} questions from {csv_file}"))
