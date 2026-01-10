# question/management/commands/normalize_exam_names2.py
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from question.models import Question  # adjust if your app label differs


def norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" \t\r\n-–—,:;")


def canonicalize(raw: str):
    if raw is None:
        return None

    s = norm(raw)
    if s == "" or s.upper() in {"(NULL)", "NULL"}:
        return None

    U = s.upper()

    # --- UPSC CSE Prelims ---
    if "CSE" in U and ("PRE" in U or "PRELIM" in U):
        return "CSE Prelims"
    if s == "CSE Prelims":
        return "CSE Prelims"

    # --- UPPCS family (aggressively merged) ---
    if "UPPCS" in U or "UPPSC" in U:
        return "UPPCS"
    if re.search(r"\bU\.?P\.?\b", U) and re.search(r"\bP\.?C\.?S\b", U):
        return "UPPCS"
    # treat UPBCS-ish strings as noisy UPPCS (condensing)
    if re.search(r"\bU\.?P\.?B\.?C\.?S\b", U) or re.search(r"\bU\.?B\.?P\.?C\.?S\b", U):
        return "UPPCS"

    # --- CDS / CAPF (strict) ---
    if U == "CDS":
        return "CDS"
    if U == "CAPF":
        return "CAPF"

    # --- BPSC ---
    if "BPSC" in U or re.search(r"\bB\.?P\.?S\.?C\b", U):
        return "BPSC"

    # --- RPSC ---
    if U == "RPSC" or re.search(r"\bRAS\b|\bRTS\b", U) or "R.A.S" in U or "R.T.S" in U:
        return "RPSC"

    # --- MPPCS ---
    if U == "MPPCS" or U == "MPPSC":
        return "MPPCS"
    if re.search(r"\bM\.?P\.?\b", U) and re.search(r"\bP\.?C\.?S\b", U):
        return "MPPCS"
    if re.search(r"\bM\.?B\.?P\.?C\.?S\b", U) or re.search(r"\bM\.?P\.?P\.?S\.?C\b", U):
        return "MPPCS"

    # --- CGPSC ---
    if U == "CGPSC" or "CHHATTIS" in U:
        return "CGPSC"

    # --- UKPSC ---
    if U == "UKPSC" or "UTTARAKHAND" in U or "UTTARANCHAL" in U or "UTTRAKHAND" in U:
        return "UKPSC"

    # --- UP Lower Subordinate ---
    if "UP LOWER SUBORDINATE" in U:
        return "UP Lower Subordinate"
    if ("LOWER" in U) and (re.search(r"\bSUB\b", U) or "SUBORD" in U):
        return "UP Lower Subordinate"
    # super-short junk like "UP Lower"
    if U == "UP LOWER":
        return "UP Lower Subordinate"

    # --- UP RO/ARO ---
    if U == "UP RO/ARO":
        return "UP RO/ARO"
    if "RO" in U and "ARO" in U and ("UP" in U or "U.P" in U):
        return "UP RO/ARO"
    if U.replace(".", "").replace(" ", "") in {"UPRO/ARO", "UPROARO"}:
        return "UP RO/ARO"

    # --- JPSC (Jharkhand) ---
    if U == "JPSC":
        return "JPSC"
    if "JHARKHAND" in U and ("PCS" in U or "P.C.S" in U):
        return "JPSC"
    if re.search(r"\bJ\.?P\.?S\.?C\b", U):
        return "JPSC"

    # --- UP UDA/LDA ---
    if U == "UP UDA/LDA":
        return "UP UDA/LDA"
    if ("UDA" in U or "U.D.A" in U) and ("LDA" in U or "L.D.A" in U):
        return "UP UDA/LDA"
    if U.replace(".", "").replace(" ", "") in {"UPUDA/LDA", "UPUDALDA"}:
        return "UP UDA/LDA"

    # --- UP BEO ---
    if U == "UP BEO" or "UPBEO" in U or re.search(r"\bB\.?E\.?O\b", U):
        return "UP RO/ARO"

    # --- B.B.S.C. (leave as-is; unclear) ---
    if U == "B.B.S.C." or U == "B.B.S.C":
        return "BPSC"

    # Fallback: keep cleaned value (so you can see leftovers in report)
    return s


class Command(BaseCommand):
    help = "Normalize Question.exam_name into a condensed canonical set (v2)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--show", type=int, default=80, help="Show first N changes")

    @transaction.atomic
    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        show_n = opts["show"]

        distinct = list(Question.objects.values_list("exam_name", flat=True).distinct())
        changes = []

        for old in distinct:
            new = canonicalize(old)
            # compare against normalized old (important: avoid churn on punctuation only)
            old_norm = None if old is None else (None if norm(old) == "" else norm(old))
            if new != old_norm:
                changes.append((old, new))

        self.stdout.write("normalize_exam_names2")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Distinct exam_name values: {len(distinct)}")
        self.stdout.write(f"Will change: {len(changes)}")
        self.stdout.write("-" * 60)

        for old, new in changes[:show_n]:
            self.stdout.write(f"{old!r}  ->  {new!r}")

        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN: no updates applied."))
            return

        updated_rows = 0
        for old, new in changes:
            if old is None:
                # nothing to filter/update safely; skip
                continue
            if new is None:
                updated_rows += Question.objects.filter(exam_name=old).update(exam_name=None)
            else:
                updated_rows += Question.objects.filter(exam_name=old).update(exam_name=new)

        self.stdout.write(self.style.SUCCESS(f"Updated rows: {updated_rows}"))
