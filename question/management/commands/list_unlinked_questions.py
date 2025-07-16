from django.core.management.base import BaseCommand
from question.models import Question

class Command(BaseCommand):
    help = "List all questions that do not have a subject (subject is NULL)"

    def handle(self, *args, **kwargs):
        unlinked_questions = Question.objects.filter(subject__isnull=True)

        if not unlinked_questions.exists():
            self.stdout.write("✅ All questions are linked to a subject.")
            return

        self.stdout.write(f"\n⚠️ Found {unlinked_questions.count()} questions without a subject:\n")

        for q in unlinked_questions:
            summary = q.question_html[:60].replace("\n", " ").replace("\r", " ")
            self.stdout.write(f"- ID {q.id} | Year: {q.year} | Subject Name: '{q.subject_name}' | Q: {summary}...")
