import csv
from django.core.management.base import BaseCommand
from question.models import Question

class Command(BaseCommand):
    help = "Export all questions from year 2000 to 2012 as a CSV file (excluding id and created_at)"

    def handle(self, *args, **kwargs):
        questions = Question.objects.filter(year__gte=2013, year__lte=2024).order_by('year')

        filename = 'questions_2013_2024.csv'
        fieldnames = [
            'year', 'subject_name', 'question_html', 'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'difficulty_level', 'nature'
        ]

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for q in questions:
                writer.writerow({
                    'year': q.year,
                    'subject_name': q.subject_name,
                    
                   
                    'question_html': q.question_html,
                    'option_a': q.option_a,
                    'option_b': q.option_b,
                    'option_c': q.option_c,
                    'option_d': q.option_d,
                    'correct_option': q.correct_option,
                    'difficulty_level': q.difficulty_level,
                    'nature': q.nature,
                    
                })

        self.stdout.write(self.style.SUCCESS(f"✅ Exported {questions.count()} questions to {filename} (excluding id and created_at)"))
