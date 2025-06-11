import csv
from django.core.management.base import BaseCommand
from question.models import Question, Subject

class Command(BaseCommand):  # ✅ Make sure this line exists and is correctly indented
    help = "Import questions from questions_2000_2012.csv into the database"

    def handle(self, *args, **kwargs):
        file_path = 'questions_2000_2012.csv'  # Adjust path if needed

        with open(file_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            count = 0
            for row in reader:
                # Match subject by ID or fallback to name
                subject = Subject.objects.filter(id=row['subject_id']).first()
                if not subject and row['subject_name']:
                    subject = Subject.objects.filter(name=row['subject_name']).first()

                Question.objects.create(
                    year=row['year'] or None,
                    subject_name=row['subject_name'],
                    subject=subject,
                    topic=row['topic'] or None,
                    subtopic=row['subtopic'] or None,
                    question_html=row['question_html'],
                    option_a=row['option_a'],
                    option_b=row['option_b'],
                    option_c=row['option_c'],
                    option_d=row['option_d'],
                    correct_option=row['correct_option'],
                    difficulty_level=row['difficulty_level'] or None,
                    nature=row['nature'] or None,
                    explanation_html=row['explanation_html'] or None,
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Imported {count} questions into the database."))
