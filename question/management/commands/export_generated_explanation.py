import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from question.models import Question


class Command(BaseCommand):
    help = "Export all questions (id, year, question_html, explanation_html) to CSV"

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            type=str,
            default="questions_export.csv",
            help="Output CSV file path",
        )

    def handle(self, *args, **options):
        out_path = Path(options["out"]).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fields = ["id", "year", "question_html", "explanation_html"]

        qs = Question.objects.all().order_by("id")

        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fields,
                quoting=csv.QUOTE_ALL,      # SAFE for HTML + commas + newlines
                lineterminator="\n",
            )
            writer.writeheader()

            for row in qs.values(*fields).iterator(chunk_size=2000):
                writer.writerow({
                    "id": row["id"],
                    "year": row["year"],
                    "question_html": row["question_html"] or "",
                    "explanation_html": row["explanation_html"] or "",
                })

        self.stdout.write(
            self.style.SUCCESS(f"Exported {qs.count()} questions to {out_path}")
        )