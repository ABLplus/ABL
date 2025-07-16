from django.core.management.base import BaseCommand
from syllabus.models import Ques
from django.db import transaction

class Command(BaseCommand):
    help = "Cleans and standardizes section_name fields in the Ques model"

    MAPPING_DICT = {
        "Context": [
            "Context",
            "Philosophical and Ideological Foundations",
        ],
        "Features": [
            "Features",
            "Features of Indian Constitution",
            "Emergency Provisions",
            "Amendment of the Constitution",
            'Amendment of the Constitution (Part XX: Article 368)',
        ],
        "Systems": [
            "Government Systems",
            "State Executive",
            "Union Executive",
            "Union Legislature",
            "State Legislature",
            "Judiciary",
            "Centre-State Relations",
        ],
        "Bodies": [
            "Bodies",
            "Constitutional Bodies",
            "Non-Constitutional Bodies",
        ],
        "Miscellaneous": [
            "Miscellaneous",
        ]
    }

    def build_reverse_map(self):
        reverse_map = {}
        for canonical, variants in self.MAPPING_DICT.items():
            for variant in variants:
                reverse_map[variant.lower().strip()] = canonical
        return reverse_map

    @transaction.atomic
    def handle(self, *args, **kwargs):
        reverse_map = self.build_reverse_map()
        updated = 0

        for q in Ques.objects.all():
            original = q.section_name.strip()
            mapped = reverse_map.get(original.lower())
            if mapped and mapped != q.section_name:
                q.section_name = mapped
                q.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Updated {updated} Ques entries with cleaned section_name values."))
