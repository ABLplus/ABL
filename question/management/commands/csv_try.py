from django.core.management.base import BaseCommand
import csv
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup, Tag



##############################################################################
# CONFIGURE HERE
##############################################################################
HTML_DIR   = Path("data/HTML files ques/Geography html")
FILE_GLOB  = "Geo_ques_1.html"
OUTPUT_CSV = "geography_questions_export.csv"

SUBJECT_NAME  = "Geography"
SECTION_NAME  = "Universe and Geo Evolution"
##############################################################################

Q_MARK_RE    = re.compile(r"---\s*Question\s+(\d+)\s*---", re.I)
EXAM_YEAR_RE = re.compile(
    r"""\[
        (.*?)\s+           # group(1) = everything before the year (non-greedy)
        (\d{4})            # group(2) = the 4-digit year
        (?:[^\]]*)]        # anything until closing ]
    """,
    re.X,
)

# optional markdown converter
try:
    from markdownify import markdownify as md
except ImportError:                      # graceful fallback
    def md(html_text, **_):
        return BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)


def clean_paragraph_html(p_html: str) -> str:
    """
    • remove trailing '[Exam 1998]' or similar
    • remove leading 'Q21.' etc.
    • return cleaned HTML string
    """
    # strip the [Exam Year] bit
    out = re.sub(r"\s*\[.*?] ?", "", p_html)

    # drop 'Q123.' inside the opening <p>
    out = re.sub(r"<p>\s*Q\d+\.\s*", "<p>", out, flags=re.I)
    return out


def gather_question_blocks(soup: BeautifulSoup):
    """
    Yields (q_no_str, list_of_Tag_elements) for every question in the file.
    """
    markers = []
    for p in soup.find_all("p"):
        if p.string and Q_MARK_RE.search(p.string):
            markers.append(p)

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


def main():
    rows = []
    for html_path in sorted(HTML_DIR.glob(FILE_GLOB)):
        unit_num = int(re.search(r"(\d+)", html_path.stem).group(1))

        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        for q_no, elems in gather_question_blocks(soup):
            if not elems:
                continue

            # split elems into [statement_parts] + options_ol
            stmt_parts = []
            options_ol = None
            for el in elems:
                if el.name == "ol" and el.get("type", "").lower() == "a":
                    options_ol = el
                    break
                stmt_parts.append(el)

            if not options_ol or len(options_ol.find_all("li")) < 4:
                continue  # skip malformed question

            # -------- build q_statement_html ---------------------------------
            cleaned_parts = []
            for part in stmt_parts:
                html_str = str(part)
                cleaned_parts.append(clean_paragraph_html(html_str))

            q_statement_html = "".join(cleaned_parts)  # keep <p>, <ol>, etc.

            # markdown version
            q_markdown = md(q_statement_html, heading_style="ATX")

            # extract exam / year (first match in statement parts)
            exam = year = ""
            for part in stmt_parts:
                txt = part.get_text(" ", strip=True)
                if (m := EXAM_YEAR_RE.search(txt)):
                    exam_raw, year = m.group(1).strip(), m.group(2)
                    exam = re.sub(r"^\d+(?:st|nd|rd|th)\s+", "", exam_raw)
                    exam = re.sub(r"\s*\([^)]*\)\s*$", "", exam)
                    break

            # options
            li = options_ol.find_all("li")
            a, b, c, d = [x.get_text(" ", strip=True) for x in li[:4]]

            rows.append(
                {
                    "unit": unit_num,
                    "q_no": q_no,
                    "q_statement_html": q_statement_html,
                    "q_markdown": q_markdown,
                    "a": a,
                    "b": b,
                    "c": c,
                    "d": d,
                    "exam": exam,
                    "year": year,
                    "subject_name": SUBJECT_NAME,
                    "section_name": SECTION_NAME,
                }
            )

    if not rows:
        print("No questions found – nothing written.")
        return

    # write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "unit",
                "q_no",
                "q_statement_html",
                "q_markdown",
                "a",
                "b",
                "c",
                "d",
                "exam",
                "year",
                "subject_name",
                "section_name",
            ],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} questions to {OUTPUT_CSV}")


class Command(BaseCommand):
    help = "Extracts MCQs from HTML files and exports as CSV."

    def handle(self, *args, **options):
        main()  # run the function from your script