from django.core.management.base import BaseCommand
from syllabus.models import Section, Ques

class Command(BaseCommand):
    help = "Print all distinct topic_name values for each Section in the Polity subject"

    def handle(self, *args, **kwargs):
        sections = Section.objects.filter(subject__name='Polity')

        for section in sections:
            self.stdout.write(self.style.SUCCESS(f"\nSection: {section.name}"))

            topics = (
                Ques.objects
                .filter(section_name=section.name)
                .values_list('topic_name', flat=True)
                .distinct()
            )

            for topic in topics:
                if topic:
                    self.stdout.write(f" - {topic}")
                else:
                    self.stdout.write(self.style.WARNING(" - [No topic name]"))



