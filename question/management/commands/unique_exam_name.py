import os
from django.core.management.base import BaseCommand

from syllabus.models import Ques
from django.db.models import Count
from syllabus.models import Ques

class Command(BaseCommand):
    help = 'Generates a report of unique exams and their question counts, including null/empty values.'

    def handle(self, *args, **kwargs):
        # Get exam counts (including None and '')
        exam_counts = (
            Ques.objects.values('exam')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

        # Prepare output directory
        output_dir = 'reports'
        os.makedirs(output_dir, exist_ok=True)

        # File path
        file_path = os.path.join(output_dir, 'exam_names.txt')

        # Write to file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write("Exam Report (Ques Count by Exam)\n")
            file.write("=" * 50 + "\n\n")
            for i, item in enumerate(exam_counts, start=1):
                exam_name = item['exam']
                if exam_name is None:
                    label = "(NULL)"
                elif exam_name.strip() == "":
                    label = "(Empty String)"
                else:
                    label = exam_name
                file.write(f"{label}: {item['total']} questions\n")

        self.stdout.write(self.style.SUCCESS(f"Report generated at: {file_path}"))



