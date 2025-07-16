# question/management/commands/import_geo_mcqs.py
import csv
import html
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from syllabus.models import Ques, Subject, Section

# ── CONFIG ──────────────────────────────────────────────────────────────.
unit=2
SUBJECT_NAME = "Science and Technology"
SECTION_NAME = "Applied Science"
DATA_DIR     = Path("data/HTML files ques/Env & Science html")
HTML_GLOB    = f"Science_Question_{unit}.html"                # question files
ANSWER_TPL   = f"science and EBCC_answer - Unit-{unit}.csv"  # answers per unit
# ────────────────────────────────────────────────────────────────────────

Q_MARK_RE = re.compile(r"---\s*Question\s+(\d+)\s*---", re.I)

EXAM_YEAR_RE = re.compile(
    r"""\[
        (.*?)\s+            # exam name (lazy)
        (\d{4})             # year
        [^\]]*]             # anything to the closing ]
    """,
    re.X,
)

try:
    from markdownify import markdownify as md
except ImportError:          # graceful fallback
    def md(html_text, **_):
        return BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)


# ── helpers ─────────────────────────────────────────────────────────────
def clean_exam_label(raw: str) -> str:
    """
    • strip leading ordinals: 65th → ''
    • remove trailing '(Pre)' etc.
    """
    s = re.sub(r"^\d+(?:st|nd|rd|th)\s+", "", raw)     # drop '65th '
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)             # drop '(Pre)'
    s = s.strip()
    return s


def clean_paragraph_html(html_str: str) -> str:
    """
    Remove '[Exam Yr]' and leading 'Q21.'; return safe HTML.
    """
    txt = re.sub(r"\s*\[.*?] ?", "", html_str)                  # strip [ … ]
    txt = re.sub(r"<p>\s*Q\d+\.\s*", "<p>", txt, flags=re.I)    # strip Q-numbers
    return txt


def gather_question_blocks(soup: BeautifulSoup):
    """
    Yield (q_no, elements[]) where elements belong to that question block.
    """
    markers = [p for p in soup.find_all("p") if p.string and Q_MARK_RE.search(p.string)]
    for idx, marker in enumerate(markers):
        q_no = Q_MARK_RE.search(marker.string).group(1)
        stop_at = markers[idx + 1] if idx + 1 < len(markers) else None
        elems = []
        cursor = marker.next_sibling
        while cursor and cursor is not stop_at:
            if isinstance(cursor, Tag):
                elems.append(cursor)
            cursor = cursor.next_sibling
        yield q_no, elems


def load_answers(unit: int) -> dict[str, str]:
    """
    Return { '87': 'b', … } for the given unit.
    """
    ans_path = DATA_DIR / ANSWER_TPL.format(unit=unit)
    if not ans_path.exists():
        return {}

    mapping: dict[str, str] = {}
    with ans_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qn = row.get("Question no", "").strip()
            sol = row.get("solution", "").strip().lower()[:1]  # keep first char
            if qn and sol:
                mapping[qn] = sol
    return mapping


# ── management command ─────────────────────────────────────────────────
class Command(BaseCommand):
    help = "Import Geography MCQs and answers into Ques model."

    def handle(self, *args, **opts):
        # ── sanity: Subject & Section must already exist ────────────────
        subject = Subject.objects.filter(name__iexact=SUBJECT_NAME).first()
        if not subject:
            raise CommandError(f'Subject "{SUBJECT_NAME}" not found – aborting.')

        section = Section.objects.filter(
            subject=subject, name__iexact=SECTION_NAME
        ).first()
        if not section:
            raise CommandError(f'Section "{SECTION_NAME}" not found – aborting.')

        objs_to_create = []

        for html_path in sorted(DATA_DIR.glob(HTML_GLOB)):
            unit = int(re.search(r"(\d+)", html_path.stem).group(1))
            answer_map = load_answers(unit)

            soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

            for q_no, elems in gather_question_blocks(soup):
                # split elems into stem parts + first choices list
                stem_parts, options_ol = [], None
                for el in elems:
                    if el.name == "ol" and el.get("type", "").lower() == "a":
                        options_ol = el
                        break
                    stem_parts.append(el)

                if not options_ol:
                    continue
                lis = options_ol.find_all("li")
                if len(lis) < 4:
                    continue  # skip malformed (expects at least a–d)

                # correct option
                correct_option = answer_map.get(q_no, "").lower()
                if correct_option not in {"a", "b", "c", "d"}:
                    correct_option = ""  # leave blank if missing or beyond d

                # statement html & markdown
                html_parts = [clean_paragraph_html(str(p)) for p in stem_parts]
                q_statement_html = "".join(html_parts)
                q_markdown = md(q_statement_html, heading_style="ATX")

                # exam / year
                exam = year = ""
                for p in stem_parts:
                    m = EXAM_YEAR_RE.search(p.get_text(" ", strip=True))
                    if m:
                        exam_raw, year = m.group(1).strip(), m.group(2)
                        exam = clean_exam_label(exam_raw)
                        break

                a, b, c, d = [li.get_text(" ", strip=True) for li in lis[:4]]

                objs_to_create.append(
                    Ques(
                        q_no=q_no,
                        q_statement=q_statement_html,
                        q_markdown=q_markdown,
                        a=a,
                        b=b,
                        c=c,
                        d=d,
                        correct_option=correct_option,
                        exam=exam,
                        year=year or None,
                        subject=subject,
                        section=section,
                        unit=unit,
                        subject_name=SUBJECT_NAME,
                        section_name=SECTION_NAME,
                    )
                )

        if not objs_to_create:
            self.stdout.write(self.style.ERROR("No questions found – nothing saved."))
            return

        with transaction.atomic():
            Ques.objects.bulk_create(objs_to_create, batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Imported {len(objs_to_create)} MCQs."))
