import csv
from django.core.management.base import BaseCommand
from question.models import Question

class Command(BaseCommand):
    help = "Export all questions from year 2013 to 2024 as a CSV file (excluding id and created_at)"

    def handle(self, *args, **kwargs):
        questions = Question.objects.filter(year__gte=2013, year__lte=2024, exam_name="CSE Prelims").order_by('year')

        filename = 'questions_2013_2024_subject-topic_yearwise.csv'
        fieldnames = [
            'year', 'subject_name', 'topic_name'
        ]

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for q in questions:
                writer.writerow({
                    'year': q.year,
                    'subject_name': q.subject_name,
                    'topic_name': q.topic_name,              
                 
                })

        self.stdout.write(self.style.SUCCESS(f"✅ Exported {questions.count()} questions to {filename} (excluding id and created_at)"))
