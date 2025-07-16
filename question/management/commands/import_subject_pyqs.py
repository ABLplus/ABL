import csv
import os
from django.core.management.base import BaseCommand
from syllabus.models import Ques, Subject, Section

class Command(BaseCommand):
    help = 'Import questions from CSV with subject and section set manually.'

    def handle(self, *args, **options):
        # 👇 Change as needed before running
        unit = 8
        csv_file_path = f"csv/AMAC/AM_combined{unit}.csv"
        subject_name = 'Art and Culture'
        # section_name = 'Later Medieval(1526-1757AD)'

        try:
            subject_obj = Subject.objects.get(name=subject_name)
            # section_obj = Section.objects.get(name=section_name, subject=subject_obj)
        except Subject.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Subject not found: '{subject_name}'"))
            return
        # except Section.DoesNotExist:
        #     self.stdout.write(self.style.ERROR(f"❌ Section not found: '{section_name}'"))
        #     return

        full_path = os.path.join(os.getcwd(), csv_file_path)

        questions_to_create = []
        count = 0

        try:
            with open(full_path, newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    raw_year = row['year'].strip()
                    year = None
                    if raw_year:
                        try:
                            year = int(raw_year.split('.')[0])
                        except ValueError:
                            self.stdout.write(self.style.WARNING(f"⚠️ Q{row['q_no']}: Invalid year '{raw_year}' — set to NULL"))

                    q = Ques(
                        q_no=row['q_no'].strip(),
                        q_statement=row['q_statement'].strip(),
                        a=row['a'].strip(),
                        b=row['b'].strip(),
                        c=row['c'].strip(),
                        d=row['d'].strip(),
                        correct_option=row['correct_option'].strip().lower(),
                        explanation=row['explanation'].strip(),
                        exam=row['exam'].strip(),
                        year=year,

                        unit=unit,
                        subject_name=subject_name,
                        # section_name=section_name,

                        subject=subject_obj,
                        # section=section_obj,

                        is_check=False,
                        for_review=False,
                    )
                    questions_to_create.append(q)
                    count += 1

                    if count % 100 == 0:
                        self.stdout.write(f"⏳ Processed {count} questions...")

            Ques.objects.bulk_create(questions_to_create, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"✅ Imported {count} questions from '{csv_file_path}' for unit {unit}"))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ File not found: {csv_file_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Unexpected error: {str(e)}"))
