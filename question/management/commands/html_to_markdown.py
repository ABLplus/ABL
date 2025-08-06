from django.core.management.base import BaseCommand
from question.models import Question # Replace with your actual app name
import html2text

class Command(BaseCommand):
    help = "Convert question_html to q_markdown for all questions"

    def handle(self, *args, **kwargs):
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.body_width = 0  # Prevent line breaks
        updated = 0

        questions = Question.objects.all()

        for question in questions:
            html_content = question.question_html or ""
            markdown = converter.handle(html_content).strip()

            question.q_markdown = markdown
            question.save(update_fields=["q_markdown"])
            updated += 1
            self.stdout.write(self.style.SUCCESS(f"✅  question {updated} to markdown"))

        self.stdout.write(self.style.SUCCESS(f"✅ Converted {updated} questions to markdown"))
