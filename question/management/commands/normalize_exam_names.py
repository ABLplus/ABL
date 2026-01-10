# question/management/commands/normalize_exam_names.py
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from question.models import Question  # adjust import

def basic_norm(s: str) -> str:
    s = (s or "").strip()
    # collapse spaces
    s = re.sub(r"\s+", " ", s)
    # remove weird trailing punctuation
    s = s.strip(" \t\r\n-–—,:;")
    return s

# Exact aliases first (cheap wins)
ALIASES = {
    "CSE Prelims": "CSE Prelims",
    "UPSC CSE Pre": "CSE Prelims",
    "UPSC CSE Pre.": "CSE Prelims",
    "UPSC CSE Pre,": "CSE Prelims",
    "UPSC CSE Pre.:": "CSE Prelims",
    "UPSC CSE Pre.": "CSE Prelims",
    "UPSC CSE": "CSE Prelims",   # if you want
    "UPSC": "CSE Prelims",       # optional

    "UPPSC": "UPPCS",
    "UPPCS": "UPPCS",
    "U.P.P.C.S.": "UPPCS",
    "U.P.P.C.S": "UPPCS",
    "U.P.P.C.S,": "UPPCS",
    "U.P.P.C.S,:": "UPPCS",
    "U.P.P.S.C.": "UPPCS",
    "U.P. P.C.S.": "UPPCS",
    "U.P.P,.C.S.:": "UPPCS",
    "U.P.P.C.S. Pre": "UPPCS",

    "BPSC": "BPSC",
    "B.P.S.C.": "BPSC",
    "B.P.S.C": "BPSC",
    "B.P.S.C,:": "BPSC",

    "RPSC": "RPSC",
    "MPPSC": "MPPCS",
    "M.P.P.C.S.": "MPPCS",
    "MPPCS": "MPPCS",

    "CGPSC": "CGPSC",
    "Chhattisgarh P.C.S.": "CGPSC",
    "Chhattisgarh PCS": "CGPSC",
    "Chhattisagarh P.C.S.": "CGPSC",
    "CPPCS": "CGPSC",

    "UKPSC": "UKPSC",
    "Uttarakhand P.C.S.": "UKPSC",
    "Uttarakhand PCS": "UKPSC",
    "Uttaranchal P.C.S.": "UKPSC",
    "Uttrakhand P.C.S.": "UKPSC",

    "JPSC": "JPSC",
    "J.P.S.C.": "JPSC",

    "CDS": "CDS",
    "CAPF": "CAPF",
    "CAPE": "CAPF",
}

def canonicalize(raw: str):
    if raw is None:
        return None
    s = basic_norm(raw)
    if s == "" or s.lower() in {"(empty string)", "empty", "none", "null"}:
        return None

    # exact alias match
    if s in ALIASES:
        return ALIASES[s]

    s2 = s.upper()

    # Family regex rules (catch the long tail)
    if re.search(r"\bUPSC\b", s2) and re.search(r"\bCSE\b|\bPRE\b|\bPRELIMS\b", s2):
        return "CSE Prelims"

    if re.search(r"\bU\.?P\.?\b", s2) and re.search(r"\bP\.?C\.?S\b", s2):
        return "UPPCS"
    if re.search(r"\bUPP?SC\b|\bUPPCS\b", s2):
        return "UPPCS"

    if re.search(r"\bB\.?P\.?S\.?C\b|\bBPSC\b", s2) or re.search(r"\bTO\s+\d+(ST|ND|RD|TH)\b.*\bBPSC\b", s2):
        return "BPSC"

    if re.search(r"\bR\.?A\.?S\b|\bR\.?T\.?S\b|\bRAS/RTS\b", s2):
        # choose ONE:
        return "RPSC"   # or "RAS/RTS"

    if re.search(r"\bM\.?P\.?\b", s2) and re.search(r"\bP\.?C\.?S\b", s2):
        return "MPPCS"
    if re.search(r"\bMPPSC\b|\bMPPCS\b", s2):
        return "MPPCS"

    if re.search(r"\bCHHATTIS", s2) or re.search(r"\bCGPSC\b|\bCPPCS\b", s2):
        return "CGPSC"

    if re.search(r"\bUTTARANCHAL\b|\bUTTRAKHAND\b|\bUTTARAKHAND\b|\bUKPSC\b", s2):
        return "UKPSC"

    if re.search(r"\bLOWER\b.*\bSUB\b", s2) and re.search(r"\bU\.?P\.?\b|\bUP\b", s2):
        return "UP Lower Subordinate"

    if re.search(r"\bR\.?O\b|\bA\.?R\.?O\b", s2) and re.search(r"\bU\.?P\.?\b|\bUP\b", s2):
        return "UP RO/ARO"

    if re.search(r"\bU\.?D\.?A\b|\bL\.?D\.?A\b", s2) and re.search(r"\bU\.?P\.?\b|\bUP\b", s2):
        return "UP UDA/LDA"

    if re.search(r"\bUPBEO\b|\bB\.?E\.?O\b", s2):
        return "UP BEO"

    # fallback: return cleaned original (or None if you prefer strict)
    return s

class Command(BaseCommand):
    help = "Normalize Question.exam_name to canonical unique names"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Do not update DB, just print changes")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of distinct names processed")

    @transaction.atomic
    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        limit = opts["limit"]

        distinct = list(
            Question.objects.exclude(exam_name__isnull=True)
            .values_list("exam_name", flat=True)
            .distinct()
        )
        if limit:
            distinct = distinct[:limit]

        changes = []
        for old in distinct:
            new = canonicalize(old)
            old_norm = basic_norm(old)
            if new != old_norm:
                changes.append((old, new))

        # Print summary
        self.stdout.write(f"Distinct exam_name: {len(distinct)}")
        self.stdout.write(f"Will change: {len(changes)}")
        for old, new in changes[:80]:
            self.stdout.write(f"- '{old}'  ->  '{new}'")

        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN: no updates applied."))
            return

        # Apply updates (bulk per old value)
        total = 0
        for old, new in changes:
            if new is None:
                updated = Question.objects.filter(exam_name=old).update(exam_name=None)
            else:
                updated = Question.objects.filter(exam_name=old).update(exam_name=new)
            total += updated

        self.stdout.write(self.style.SUCCESS(f"Updated rows: {total}"))
