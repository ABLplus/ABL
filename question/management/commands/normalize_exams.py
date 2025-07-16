# from django.core.management.base import BaseCommand
# from syllabus.models import Ques

# class Command(BaseCommand):
#     help = 'Normalizes the exam names in Ques table using a predefined mapping.'

#     def handle(self, *args, **options):
#         # Canonical exam name mapping
#         exam_mapping = {
#           "U.P.P.C.S. (Pre) (Re-Exam)": "UPPCS Prelims",
#     "U.P.P.C.S. (Pre) (Re. Exam)": "UPPCS Prelims",
#     "U.P.B.C.S. (Pre)": "UPPCS Prelims",
#     "U.P.B.C.S. Pre": "UPPCS Prelims",
#     "U.P.B.C.S, (Pre)": "UPPCS Prelims",
#     "U.P, Lower Sub. (Spl) (Pre)": "UPPCS Lower Prelims",
#     "CDS  (IT)": "CDS Prelims I",
#     "CDS  (1:": "CDS Prelims I",
#     "CDS (D:": "CDS General",
#     "CDS  (D:": "CDS General",
#     "CDS  (11:": "CDS General",
#     "CDS Pre. 11": "CDS Prelims I",
#     "CDS Pre.  T": "CDS General",
#     "CDS Pre.  (D:": "CDS General",
#     "RAS/RTS": "RAS/RTS Prelims",
#     "R.A.S./R.T.S.(Pre:": "RAS/RTS Prelims",
#     "U.P.P.C.S. (Sp:": "UPPCS Mains",
#     "U.P.P.S.C. (SpI) (Pre)": "UPPCS Prelims",
#     "U.P.U.D.A./L.D.A. (Pre)": "UPPCS Prelims",
#     "U.BS.C (Pre)": "UPPCS Prelims",
#     "U.B.P.C.S. (Pre)": "UPPCS Prelims",
#     "U.B.B.C.S. (Pre)": "UPPCS Prelims",
#     "MPPCS": "MPPCS General",
#     "CDS": "CDS General",
#     "CGPCS": "CGPCS Prelims",
#     "UKPCS": "UKPCS Prelims",
#     "Jharkhand PCS": "Jharkhand PCS Prelims",
#     # BPSC series
#     "40th B.P.S.C. (Pre)": "BPSC Prelims",
#     "63rd B.P.S.C. (Pre)": "BPSC Prelims",
#     "60th to 62nd B.P.S.C. (Pre)": "BPSC Prelims",
#     "53rd to 55th B.P.S.C. (Pre)": "BPSC Prelims",
#     "53rd to 55th B.B.S.C. (Pre)": "BPSC Prelims",
#     "45th B.P.S.C. (Pre)": "BPSC Prelims",
#     "41st B.P.S.C. (Pre)": "BPSC Prelims",
#     "67th BB.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
#     "67th B.P.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
#     "67th B.P.S.C, (Pre),": "BPSC Prelims",
#     "67th B.B.S.C. (Pre),": "BPSC Prelims",
#     "67 B.P.S.C. (Pre)": "BPSC Prelims",
#     "66th B.P.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
#     "66th B.B.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
#     '66"* BPSC (Pre, Re-Exam)': "BPSC Prelims",
#     '66" B.P.S.C. (Pre)': "BPSC Prelims",
#     "64th B.P.C.S. (Pre)": "BPSC Prelims",
#     "60 to 62° B.B.S.C. (Pre)": "BPSC Prelims",
#     '53"4 to 55" BPSC Pre': "BPSC Prelims",
#     "48th to 52nd B.P.S.C, (Pre)": "BPSC Prelims",
#     "47th B.P.S.C. (Pre)": "BPSC Prelims",
#     "47 B.P.S.C. (Pre)": "BPSC Prelims",
#     "45 B.P.S.C, (Pre)": "BPSC Prelims",
#     "43 BPSC Pre": "BPSC Prelims",
#     "42nd B.P.S.C. (Pre)": "BPSC Prelims",
#     "42nd B.P.C.S. (Pre)": "BPSC Prelims",
#     "42nd B.BS.C. (Pre)": "BPSC Prelims",
#     "41st B.B.S.C. (Pre)": "BPSC Prelims",
#     "40th B.B.S.C, (Pre)": "BPSC Prelims",
#     '39" B.P.S.C. (Pre)': "BPSC Prelims",
#     "38th B.P.S.C. (Pre)": "BPSC Prelims",
#         }

#         updated = 0
#         to_update = []

#         for ques in Ques.objects.all():
#             key = ques.exam.strip() if ques.exam else "(NULL)"
#             new_exam = exam_mapping.get(key)

#             if new_exam is not None and ques.exam != new_exam:
#                 ques.exam = new_exam
#                 to_update.append(ques)
#                 self.stdout.write(f"Updated Ques ID {ques.id} exam from '{key}' to '{new_exam}'")

#         if to_update:
#             Ques.objects.bulk_update(to_update, ['exam'])
#             updated = len(to_update)
#             self.stdout.write(self.style.SUCCESS(f"✅ Successfully updated {updated} Ques entries."))

#         self.stdout.write(self.style.SUCCESS(f"Updated {updated} Ques entries with normalized exam names."))



from django.core.management.base import BaseCommand
from syllabus.models import Ques

class Command(BaseCommand):
    help = 'Normalize exam names in Ques using a predefined mapping.'

    def handle(self, *args, **options):
        # Mapping should be defined above this block or imported
        exam_mapping = {
             "U.P.P.C.S. (Pre) (Re-Exam)": "UPPCS Prelims",
    "U.P.P.C.S. (Pre) (Re. Exam)": "UPPCS Prelims",
    "U.P.B.C.S. (Pre)": "UPPCS Prelims",
    "U.P.B.C.S. Pre": "UPPCS Prelims",
    "U.P.B.C.S, (Pre)": "UPPCS Prelims",
    "U.P, Lower Sub. (Spl) (Pre)": "UPPCS Lower Prelims",
    "CDS  (IT)": "CDS Prelims I",
    "CDS  (1:": "CDS Prelims I",
    "CDS (D:": "CDS General",
    "CDS  (D:": "CDS General",
    "CDS  (11:": "CDS General",
    "CDS Pre. 11": "CDS Prelims I",
    "CDS Pre.  T": "CDS General",
    "CDS Pre.  (D:": "CDS General",
    "RAS/RTS": "RAS/RTS Prelims",
    "R.A.S./R.T.S.(Pre:": "RAS/RTS Prelims",
    "U.P.P.C.S. (Sp:": "UPPCS Mains",
    "U.P.P.S.C. (SpI) (Pre)": "UPPCS Prelims",
    "U.P.U.D.A./L.D.A. (Pre)": "UPPCS Prelims",
    "U.BS.C (Pre)": "UPPCS Prelims",
    "U.B.P.C.S. (Pre)": "UPPCS Prelims",
    "U.B.B.C.S. (Pre)": "UPPCS Prelims",
    "MPPCS": "MPPCS General",
    "CDS": "CDS General",
    "CGPCS": "CGPCS Prelims",
    "UKPCS": "UKPCS Prelims",
    "Jharkhand PCS": "Jharkhand PCS Prelims",
    # BPSC series
    "40th B.P.S.C. (Pre)": "BPSC Prelims",
    "63rd B.P.S.C. (Pre)": "BPSC Prelims",
    "60th to 62nd B.P.S.C. (Pre)": "BPSC Prelims",
    "53rd to 55th B.P.S.C. (Pre)": "BPSC Prelims",
    "53rd to 55th B.B.S.C. (Pre)": "BPSC Prelims",
    "45th B.P.S.C. (Pre)": "BPSC Prelims",
    "41st B.P.S.C. (Pre)": "BPSC Prelims",
    "67th BB.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
    "67th B.P.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
    "67th B.P.S.C, (Pre),": "BPSC Prelims",
    "67th B.B.S.C. (Pre),": "BPSC Prelims",
    "67 B.P.S.C. (Pre)": "BPSC Prelims",
    "66th B.P.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
    "66th B.B.S.C. (Pre) (Re-Exam),": "BPSC Prelims",
    '66"* BPSC (Pre, Re-Exam)': "BPSC Prelims",
    '66" B.P.S.C. (Pre)': "BPSC Prelims",
    "64th B.P.C.S. (Pre)": "BPSC Prelims",
    "60 to 62° B.B.S.C. (Pre)": "BPSC Prelims",
    '53"4 to 55" BPSC Pre': "BPSC Prelims",
    "48th to 52nd B.P.S.C, (Pre)": "BPSC Prelims",
    "47th B.P.S.C. (Pre)": "BPSC Prelims",
    "47 B.P.S.C. (Pre)": "BPSC Prelims",
    "45 B.P.S.C, (Pre)": "BPSC Prelims",
    "43 BPSC Pre": "BPSC Prelims",
    "42nd B.P.S.C. (Pre)": "BPSC Prelims",
    "42nd B.P.C.S. (Pre)": "BPSC Prelims",
    "42nd B.BS.C. (Pre)": "BPSC Prelims",
    "41st B.B.S.C. (Pre)": "BPSC Prelims",
    "40th B.B.S.C, (Pre)": "BPSC Prelims",
    '39" B.P.S.C. (Pre)': "BPSC Prelims",
    "38th B.P.S.C. (Pre)": "BPSC Prelims",
        }

        to_update = []
        updated = 0

        for ques in Ques.objects.all():
            key = ques.exam.strip() if ques.exam else "(NULL)"
            new_exam = exam_mapping.get(key)

            if new_exam is not None and ques.exam != new_exam:
                ques.exam = new_exam
                to_update.append(ques)
                self.stdout.write(
                    f"🔄 Ques ID {ques.id}: '{key}' → '{new_exam}'"
                )

        if to_update:
            Ques.objects.bulk_update(to_update, ['exam'])
            updated = len(to_update)
            self.stdout.write(self.style.SUCCESS(
                f"✅ Successfully updated {updated} Ques entries."
            ))
        else:
            self.stdout.write(self.style.WARNING("⚠️ No entries needed updating."))

        self.stdout.write(self.style.SUCCESS(
            f"🎉 Normalization process complete."
        ))