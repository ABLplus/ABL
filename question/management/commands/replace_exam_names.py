from django.core.management.base import BaseCommand
from django.db import transaction
from question.models import Question


# 👉 EDIT THIS DICTIONARY AS YOU WISH
EXAM_REPLACE = {

    # ---------------- UPSC CSE PRELIMS ----------------
    "CSE Prelims": "CSE Prelims",
    "UPSC CSE Pre": "CSE Prelims",
    "UPSC CSE Pre.": "CSE Prelims",
    "UPSC CSE Pre,": "CSE Prelims",
    "UPSC CSE Pre,:": "CSE Prelims",
    "UPSC CSE": "CSE Prelims",
    "U.P.S.C.": "CSE Prelims",
    # "UPSC": "CSE Prelims",  # OPTIONAL: uncomment only if UPSC always means CSE Prelims in your DB

    # ---------------- CDS / CAPF ----------------
    "CDS": "CDS",
    "CAPF": "CAPF",
    "CAPE": "CAPF",  # typo

    # ---------------- UPPSC (UP PCS) ----------------
    "U.P.P.C.S.": "UPPSC",
    "U.P.P.C.S": "UPPSC",
    "U.P.P.C.S,:": "UPPSC",
    "U.P.P.C.S,": "UPPSC",
    "U.P.P.C.S,.:": "UPPSC",
    "U.P.P.C.S, (Pre)": "UPPSC",
    "U.P.P.C.S (Pre)": "UPPSC",
    "U.P.P.C.S. (Pre)": "UPPSC",
    "U.P.P.C.S.(Pre)": "UPPSC",
    "U.P.P.C.S. Pre": "UPPSC",
    "U.P.P.C.S Pre": "UPPSC",
    "U.P.P.C.S. (Spl)": "UPPSC",
    "U.P.P.C.S. (Spl.)": "UPPSC",
    "U.P.P.C.S. (Spl):": "UPPSC",
    "U.P.P.C.S.(Spl)": "UPPSC",
    "U.P.P.C.S (Spl)": "UPPSC",
    "U.P.P.C.S, (Spl)": "UPPSC",
    "U.P.P.C.S (Spl):": "UPPSC",
    "U.P.P.C.S (pl)": "UPPSC",
    "U.P.P.C.S. (Re-Exam)": "UPPSC",
    "U.P.P.C.S. (Re. Exam)": "UPPSC",
    "U.P.P.C.S. (Mains) Spl.": "UPPSC",
    "U.P.P.S.C.": "UPPSC",
    "U.P. P.C.S.:": "UPPSC",
    "U.P. P.C.S.": "UPPSC",
    "U.P. P.C.S. (Spl.):": "UPPSC",
    "U.P.P,.C.S.:": "UPPSC",
    "U.P.P,.C.S.": "UPPSC",
    "UPPSC": "UPPSC",
    "UPPCS": "UPPSC",
    "UPPCS (Pre)": "UPPSC",
    "UPPCS (Spl)": "UPPSC",
    "U.P.B.C.S.": "UPPSC",
    "U.B.P.C.S.": "UPPSC",
    "U.P.BC.S. (Spi)": "UPPSC",
    "U.P.B.C.S. (Spl.)": "UPPSC",

    # ---------------- BPSC ----------------
    "B.P.S.C.": "BPSC",
    "B.P.S.C": "BPSC",
    "B.P.S.C,:": "BPSC",
    "B.P.S.C,": "BPSC",
    "BPSC": "BPSC",
    "BPSC (Pre)": "BPSC",
    "B.P.S.C. (Pre)": "BPSC",
    "B.P.S.C.(Pre)": "BPSC",
    "B.P.S.C.(Pre):": "BPSC",
    "BPSC (Re-Exam)": "BPSC",
    "B.P.S.C. Re-Exam": "BPSC",
    "B.P.S.C. Re-Exam:": "BPSC",
    "to 62nd B.P.S.C.": "BPSC",
    "to 59th B.P.S.C.": "BPSC",
    "to 52nd B.P.S.C.": "BPSC",
    "to 55th B.P.S.C.": "BPSC",
    "to 62nd BPSC": "BPSC",
    "to 55th BPSC": "BPSC",
    "to 59th BPSC": "BPSC",
    "to 52nd B.PS.C.": "BPSC",
    "52nd B.P.S.C.": "BPSC",
    "64 BPSC": "BPSC",
    "67 BPSC (Pre)": "BPSC",
    "67 B.P.S.C. (Pre)": "BPSC",
    "67 B.P.S.C.": "BPSC",
    "B.B.S.C.": "BPSC",

    # ---------------- RPSC (RAS/RTS family) ----------------
    "RPSC": "RPSC",
    "R.A.S./R.T.S.": "RPSC",
    "R.A.S./R.T.S": "RPSC",
    "R.A.S./R.T.S,:": "RPSC",
    "R.A.S./ R.T.S.": "RPSC",
    "R.A.S/R.T.S.": "RPSC",
    "R.A.S/RTS": "RPSC",
    "R.A.S.": "RPSC",
    "RAS/RTS": "RPSC",
    "RAS/RTS (Pre)": "RPSC",
    "RAS/RTS (Re-Exam)": "RPSC",
    "R.A.S./R.T.S. (Pre)": "RPSC",
    "R.A.S./R.T.S.(Pre)": "RPSC",
    "R.A.S/RTS (Pre)": "RPSC",
    "R.A.S./R.T.S. (Re-Exam)": "RPSC",
    "R.A.S./R.T.S. (Re. Exam)": "RPSC",
    "R.A.S./R.T.S. (Pre):": "RPSC",
    "R.A.S./R.T.S:": "RPSC",
    "R.A.S./R.E.S.": "RPSC",

    # ---------------- MPPSC ----------------
    "M.P.P.C.S.": "MPPSC",
    "M.P.P.C.S": "MPPSC",
    "M.P.P.C.S,:": "MPPSC",
    "M.P.P.C.S,": "MPPSC",
    "M.P.P.S.C.": "MPPSC",
    "M.B.P.C.S.": "MPPSC",
    "MPPSC": "MPPSC",
    "MPPCS": "MPPSC",
    "MPPCS Pre": "MPPSC",
    "MPPCS Pre:": "MPPSC",
    "MPPCS Pre ": "MPPSC",
    "MPPCS Pre": "MPPSC",

    # ---------------- CGPSC ----------------
    "CGPSC": "CGPSC",
    "Chhattisgarh P.C.S.": "CGPSC",
    "Chhattisgarh P.C.S": "CGPSC",
    "Chhattisgarh P.C.S,:": "CGPSC",
    "Chhattisgarh PCS": "CGPSC",
    "Chhattisgarh PCS:": "CGPSC",
    "Chhattisagarh P.C.S.": "CGPSC",
    "CPPCS": "CGPSC",

    # ---------------- UKPSC ----------------
    "UKPSC": "UKPSC",
    "Uttarakhand P.C.S.": "UKPSC",
    "Uttarakhand P.C.S": "UKPSC",
    "Uttarakhand PCS": "UKPSC",
    "Uttaranchal P.C.S.": "UKPSC",
    "Uttrakhand P.C.S.": "UKPSC",
    "Uttrakhand P.C.S.:": "UKPSC",
    "Uttarakhand P.C.S.:": "UKPSC",
    "Uttarakhand P.C.S. (J)": "UKPSC",
    "Uttarakhand Lower Sub.": "UKPSC",
    "Uttarakhand Lower (Sub.)": "UKPSC",
    "Uttarakhand Lower (Sub)": "UKPSC",
    "Uttarakhand E.C.S.": "UKPSC",

    # ---------------- JPSC ----------------
    "JPSC": "JPSC",
    "J.P.S.C.": "JPSC",
    "Jharkhand P.C.S.": "JPSC",
    "Jharkhand P.C.S": "JPSC",
    "Jharkhand P.C.S,:": "JPSC",
    "Jharkhand PCS": "JPSC",

    # ---------------- UP LOWER SUB ----------------
    "U.P. Lower Sub.": "UP Lower Subordinate",
    "UP Lower Sub.": "UP Lower Subordinate",
    "U.P.Lower Sub.": "UP Lower Subordinate",
    "U.P.Lower Sub": "UP Lower Subordinate",
    "UP Lower Sub.:": "UP Lower Subordinate",
    "UP Lower:": "UP Lower Subordinate",
    "UP Lower": "UP Lower Subordinate",
    "UP Lower (Sub)": "UP Lower Subordinate",
    "U.P. Lower Sub": "UP Lower Subordinate",
    "U.P Lower Sub.": "UP Lower Subordinate",

    # Spl variants (still same canonical)
    "U.P. Lower Sub. (Spl)": "UP Lower Subordinate",
    "U.P. Lower Sub. (Spl.)": "UP Lower Subordinate",
    "U.P Lower Sub.(Spl)": "UP Lower Subordinate",
    "U.P Lower Sub.(Spl):": "UP Lower Subordinate",
    "U.P Lower Sub.(Spl)": "UP Lower Subordinate",
    "U.P.Lower Sub.(Spl)": "UP Lower Subordinate",
    "UP.Lower Sub.(Spl)": "UP Lower Subordinate",
    "UP Lower Sub.(Spl)": "UP Lower Subordinate",
    "UP Lower Sub. (Spl)": "UP Lower Subordinate",
    "UP Lower Sub. (Spl):": "UP Lower Subordinate",
    "U.P. Lower (Spl.)": "UP Lower Subordinate",
    "U.P. Lower (Spl):": "UP Lower Subordinate",
    "U.P. Lower (Spl)": "UP Lower Subordinate",
    "U.P.Lower (Spl)": "UP Lower Subordinate",
    "U.P. Lower Spl.": "UP Lower Subordinate",
    "U.P. Lower (Spl.)": "UP Lower Subordinate",
    "U.P. Lower (Spl)": "UP Lower Subordinate",

    # ---------------- UP RO/ARO ----------------
    "U.P. R.O./A.R.O.": "UP RO/ARO",
    "U.P.R.O./A.R.O.": "UP RO/ARO",
    "U.P.R.O./A.R.O.:": "UP RO/ARO",
    "UP RO/ARO": "UP RO/ARO",
    "UP RO/ARO:": "UP RO/ARO",
    "UPRO/ARO": "UP RO/ARO",
    "U.P. RO/ARO": "UP RO/ARO",
    "U.P. RO/ARO:": "UP RO/ARO",
    "U.P. R.O./A.R.O., (Pre)": "UP RO/ARO",

    # ---------------- UP UDA/LDA ----------------
    "U.P.U.D.A./L.D.A.": "UP UDA/LDA",
    "U.P. U.D.A./L.D.A.": "UP UDA/LDA",
    "U.P.U.D.A/L.D.A.": "UP UDA/LDA",
    "U.P.U.D.A/L.D.A.:": "UP UDA/LDA",
    "UPUDA/LDA": "UP UDA/LDA",
    "Uttrakhand U.D.A./L.D.A.": "UP UDA/LDA",  # if this is actually Uttarakhand, split later; in your data it's 1 row only

    # ---------------- UP BEO ----------------
    "UPBEO": "UP BEO",
    "U.P.B.E.O.": "UP BEO",
    "U.P.B.E.O.:": "UP BEO",

    # ---------------- Rare / Unknown / Empty ----------------
    "(Empty String)": None,
    "": None,

    # This appears 5 times in your report. It’s probably a typo / unknown exam.
    

    # These appear twice each; unclear meaning.
    

    # Very low frequency - decide later
    
}



def basic_norm(s: str) -> str:
    if s is None:
        return ""
    return s.strip()


class Command(BaseCommand):
    help = "Replace Question.exam_name values using a fixed mapping dictionary"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without updating the database",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Fetch distinct existing values
        distinct_values = (
            Question.objects
            .values_list("exam_name", flat=True)
            .distinct()
        )

        changes = []

        for old in distinct_values:
            old_norm = basic_norm(old)

            if old_norm in EXAM_REPLACE:
                new = EXAM_REPLACE[old_norm]
                changes.append((old, new))

        self.stdout.write(f"Found {len(changes)} exam_name values to replace.\n")

        # Show preview
        for old, new in changes:
            self.stdout.write(f"'{old}'  →  '{new}'")

        if dry_run:
            self.stdout.write("\nDRY RUN: No database updates performed.")
            return

        # Apply updates
        total_updated = 0
        for old, new in changes:
            if new is None:
                updated = Question.objects.filter(exam_name=old).update(exam_name=None)
            else:
                updated = Question.objects.filter(exam_name=old).update(exam_name=new)
            total_updated += updated

        self.stdout.write(
            self.style.SUCCESS(f"\nUpdated {total_updated} Question rows.")
        )
