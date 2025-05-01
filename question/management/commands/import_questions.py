import os
import csv

from django.conf import settings  # <-- New import
from django.core.management.base import BaseCommand
from question.models import Question

class Command(BaseCommand):
    help = 'Import questions from CSV files located in question/csv_files/'

    def handle(self, *args, **options):
        # Build the full absolute path
        csv_folder_path = os.path.join(settings.BASE_DIR, 'question', 'csv_files')

        if not os.path.exists(csv_folder_path):
            self.stdout.write(self.style.ERROR(f"❌ Folder {csv_folder_path} does not exist."))
            return

        for filename in os.listdir(csv_folder_path):
            if filename.endswith('.csv'):
                year_part = filename.split('.')[0]
                try:
                    year = int(year_part)
                except ValueError:
                    self.stdout.write(self.style.WARNING(f"⚠️ Skipping file {filename} because year could not be determined."))
                    continue

                file_path = os.path.join(csv_folder_path, filename)

                with open(file_path, newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        Question.objects.create(
                            source_type='PYQ',
                            year=year,
                            subject=row.get('Subject', ''),
                            topic=None,
                            subtopic=None,
                            question_html=row.get('Question_HTML', ''),
                            option_a=row.get('Option_A', ''),
                            option_b=row.get('Option_B', ''),
                            option_c=row.get('Option_C', ''),
                            option_d=row.get('Option_D', ''),
                            correct_option=row.get('Correct Option', ''),
                            difficulty_level=row.get('Difficulty Level', ''),
                            nature=row.get('Nature', ''),
                            explanation_html=row.get('Explanation_HTML', '')
                        )
                self.stdout.write(self.style.SUCCESS(f"✅ Imported questions for year {year}"))

        self.stdout.write(self.style.SUCCESS("🎯 All CSV files processed successfully!"))
