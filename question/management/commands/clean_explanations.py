from django.core.management.base import BaseCommand
from question.models import Question
from bs4 import BeautifulSoup

class Command(BaseCommand):
    help = "Cleans <td> wrappers from explanation_html"

    def handle(self, *args, **kwargs):
        questions = Question.objects.filter(explanation_html__icontains='<td')
        print(f"Found {questions.count()} questions with <td> in explanation.")

        for q in questions:
            self.stdout.write("=" * 80)
            self.stdout.write(f"QUESTION ID: {q.id}\n")

            self.stdout.write("--- BEFORE ---")
            self.stdout.write(q.explanation_html.strip())

            soup = BeautifulSoup(q.explanation_html, 'html.parser')
            td = soup.find('td')

            if td:
                cleaned = td.decode_contents()
                self.stdout.write("\n--- AFTER ---")
                self.stdout.write(cleaned.strip())

                q.explanation_html = cleaned
                q.save()
                self.stdout.write("\n✅ Saved.\n")
            else:
                self.stdout.write("\n⚠️ <td> not found, skipping.\n")