from django.core.management.base import BaseCommand
from syllabus.models import Ques, Subject, Section, Topic
import re

# 🔧 Change these two variables as needed
SUBJECT_NAME = "Polity"
SECTION_NAME = "Systems"

def normalize(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip().lower().replace('–', '-').replace('—', '-'))

class Command(BaseCommand):
    help = "Attach Subject, Section, and Topic FKs to Ques using name fields. Topic applied for specified section."

    def handle(self, *args, **kwargs):
        updated_subject_section = 0
        skipped_subject_section = 0

        self.stdout.write(f"\n🔄 Linking Subject and Section for all Ques...")

        # Step 1: Attach Subject and Section
        for q in Ques.objects.all():
            changed = False

            if not q.subject and q.subject_name:
                q.subject = Subject.objects.filter(name=q.subject_name.strip()).first()
                if q.subject:
                    changed = True
                else:
                    skipped_subject_section += 1
                    continue

            if not q.section and q.section_name and q.subject:
                q.section = Section.objects.filter(
                    subject=q.subject,
                    name=q.section_name.strip()
                ).first()
                if q.section:
                    changed = True
                else:
                    skipped_subject_section += 1
                    continue

            if changed:
                q.save()
                updated_subject_section += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Subject/Section linking done. Updated: {updated_subject_section}, Skipped: {skipped_subject_section}"
        ))

        # Step 2: Attach Topic for specific section
        self.stdout.write(f"\n🔄 Linking Topics in section '{SECTION_NAME}'...")

        try:
            section = Section.objects.get(name=SECTION_NAME.strip(), subject__name=SUBJECT_NAME.strip())
        except Section.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Section '{SECTION_NAME}' under subject '{SUBJECT_NAME}' not found."))
            return

        topics = Topic.objects.filter(section=section)
        topic_map = {normalize(t.name): t for t in topics}

        updated_topic = 0
        unmatched_topic = 0

        ques_queryset = Ques.objects.filter(section=section)

        for q in ques_queryset:
            norm_topic = normalize(q.topic_name)

            if norm_topic in topic_map:
                q.topic = topic_map[norm_topic]
                q.save()
                updated_topic += 1
            else:
                unmatched_topic += 1
                self.stdout.write(self.style.WARNING(f"⚠ No matching Topic for Q{q.q_no}: '{q.topic_name}'"))

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Topic linking complete in '{SECTION_NAME}'. Updated: {updated_topic}, Unmatched: {unmatched_topic}"
        ))
