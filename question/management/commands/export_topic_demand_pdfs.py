
from django.core.management.base import BaseCommand, CommandError
import os
import re
from dataclasses import dataclass
from typing import List, Optional


from django.db.models import Prefetch
from django.utils.text import slugify

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    ListFlowable,
    ListItem,
    Preformatted,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ✅ Update this import path to wherever your models live
from syllabus.models import Subject, Section, Topic, TopicDemand


# ----------------------------
# Minimal Markdown -> Flowables
# ----------------------------

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")  # naive *italic*

def md_inline_to_rl(text: str) -> str:
    """Convert a subset of Markdown inline formatting to ReportLab Paragraph tags."""
    # Escape bare ampersands to avoid XML issues
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = BOLD_RE.sub(r"<b>\1</b>", text)
    text = ITALIC_RE.sub(r"<i>\1</i>", text)
    # inline code `x` -> <font face="Courier">x</font>
    text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
    return text


def markdown_to_flowables(md: str, styles) -> List:
    """
    Convert basic Markdown to ReportLab flowables:
    - #, ##, ### headings
    - bullet lists (-, *)
    - numbered lists (1., 2., ...)
    - fenced code blocks ``` ```
    - paragraphs
    """
    flow = []
    if not md:
        return flow

    lines = md.splitlines()
    i = 0

    bullet_items: List[str] = []
    number_items: List[str] = []

    def flush_bullets():
        nonlocal bullet_items
        if bullet_items:
            lst = ListFlowable(
                [ListItem(Paragraph(md_inline_to_rl(x), styles["Body"])) for x in bullet_items],
                bulletType="bullet",
                leftIndent=18,
                bulletFontName="Helvetica",
                bulletFontSize=10,
            )
            flow.append(lst)
            flow.append(Spacer(1, 6))
            bullet_items = []

    def flush_numbers():
        nonlocal number_items
        if number_items:
            lst = ListFlowable(
                [ListItem(Paragraph(md_inline_to_rl(x), styles["Body"])) for x in number_items],
                bulletType="1",
                start="1",
                leftIndent=18,
            )
            flow.append(lst)
            flow.append(Spacer(1, 6))
            number_items = []

    while i < len(lines):
        line = lines[i].rstrip()

        # code fence
        if line.strip().startswith("```"):
            flush_bullets()
            flush_numbers()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            # skip closing fence if present
            if i < len(lines) and lines[i].strip().startswith("```"):
                i += 1

            code_text = "\n".join(code_lines).replace("\t", "    ")
            flow.append(Preformatted(code_text, styles["Code"]))
            flow.append(Spacer(1, 10))
            continue

        # blank line
        if not line.strip():
            flush_bullets()
            flush_numbers()
            flow.append(Spacer(1, 6))
            i += 1
            continue

        # headings
        if line.startswith("#"):
            flush_bullets()
            flush_numbers()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            title = md_inline_to_rl(title)

            if level == 1:
                flow.append(Paragraph(title, styles["H1"]))
            elif level == 2:
                flow.append(Paragraph(title, styles["H2"]))
            else:
                flow.append(Paragraph(title, styles["H3"]))
            flow.append(Spacer(1, 8))
            i += 1
            continue

        # bullets
        m_b = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m_b:
            flush_numbers()
            bullet_items.append(m_b.group(1).strip())
            i += 1
            continue

        # numbers
        m_n = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m_n:
            flush_bullets()
            number_items.append(m_n.group(1).strip())
            i += 1
            continue

        # paragraph
        flush_bullets()
        flush_numbers()

        # join subsequent non-empty lines that are not new blocks into one paragraph
        para_lines = [line.strip()]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].rstrip()
            if not nxt.strip():
                break
            if nxt.startswith("#") or re.match(r"^\s*[-*]\s+", nxt) or re.match(r"^\s*\d+\.\s+", nxt) or nxt.strip().startswith("```"):
                break
            para_lines.append(nxt.strip())
            j += 1

        para_text = md_inline_to_rl(" ".join(para_lines))
        flow.append(Paragraph(para_text, styles["Body"]))
        flow.append(Spacer(1, 8))
        i = j

    flush_bullets()
    flush_numbers()
    return flow


# ----------------------------
# PDF helpers
# ----------------------------

def sanitize_filename(s: str) -> str:
    s = slugify(s)[:120] or "file"
    return s


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(A4[0] - 0.6 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_styles():
    base = getSampleStyleSheet()

    styles = {
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceAfter=12,
        ),
        "SectionTitle": ParagraphStyle(
            "SectionTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            spaceAfter=10,
        ),
        "TopicTitle": ParagraphStyle(
            "TopicTitle",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            spaceAfter=6,
        ),
        "Meta": ParagraphStyle(
            "Meta",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=colors.grey,
            spaceAfter=8,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceAfter=6,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            spaceAfter=4,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            spaceAfter=3,
        ),
        "Code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=9.5,
            leading=12,
            backColor=colors.whitesmoke,
            borderPadding=6,
        ),
    }
    return styles


# ----------------------------
# Management Command
# ----------------------------

class Command(BaseCommand):
    help = "Generate one PDF per Section for a Subject, containing TopicDemand Markdown for each Topic."

    def add_arguments(self, parser):
        parser.add_argument("--subject-id", type=int, required=True, help="Subject ID (e.g. 4)")
        parser.add_argument(
            "--exam-name",
            type=str,
            default="UPSC CSE (Prelims)",
            help="TopicDemand.exam_name to pick (default: UPSC CSE (Prelims))",
        )
        parser.add_argument(
            "--outdir",
            type=str,
            default="exports/topic_demand_pdfs",
            help="Output directory (relative to project root unless absolute).",
        )
        parser.add_argument(
            "--include-missing",
            action="store_true",
            help="If set, topics without a matching TopicDemand will still appear with a placeholder.",
        )

    def handle(self, *args, **opts):
        subject_id = opts["subject_id"]
        exam_name = opts["exam_name"]
        outdir = opts["outdir"]
        include_missing = opts["include_missing"]

        subject = Subject.objects.filter(id=subject_id).select_related("exam").first()
        if not subject:
            raise CommandError(f"Subject with id={subject_id} not found.")

        # ensure outdir exists
        if not os.path.isabs(outdir):
            outdir = os.path.join(os.getcwd(), outdir)
        os.makedirs(outdir, exist_ok=True)

        styles = build_styles()

        # Prefetch topics and topicdemands efficiently
        sections = (
            Section.objects.filter(subject_id=subject_id)
            .prefetch_related(
                Prefetch(
                    "topics",
                    queryset=Topic.objects.all().order_by("id"),
                )
            )
            .order_by("id")
        )

        # Preload TopicDemand into a dict keyed by (topic_id) for the exam_name
        demands = (
            TopicDemand.objects.filter(subject_id=subject_id, exam_name=exam_name)
            .select_related("topic", "section", "subject")
        )
        demand_by_topic_id = {d.topic_id: d for d in demands}

        generated = 0
        skipped_sections = 0

        for section in sections:
            topics = list(section.topics.all())

            # Decide if this section should produce a PDF at all
            has_any = any(t.id in demand_by_topic_id for t in topics)
            if not has_any and not include_missing:
                skipped_sections += 1
                continue

            filename = f"{sanitize_filename(subject.name)}__{sanitize_filename(section.name)}__{sanitize_filename(exam_name)}.pdf"
            outpath = os.path.join(outdir, filename)

            doc = SimpleDocTemplate(
                outpath,
                pagesize=A4,
                leftMargin=0.75 * inch,
                rightMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
                title=f"{subject.name} - {section.name} ({exam_name})",
                author="Django Export",
            )

            story = []

            # Cover / Header
            story.append(Paragraph(f"{md_inline_to_rl(subject.name)}", styles["Title"]))
            story.append(Paragraph(f"{md_inline_to_rl(section.name)}", styles["SectionTitle"]))
            story.append(Paragraph(md_inline_to_rl(f"Exam: **{exam_name}**"), styles["Meta"]))
            story.append(Spacer(1, 12))

            # Content per topic
            for idx, topic in enumerate(topics, start=1):
                demand: Optional[TopicDemand] = demand_by_topic_id.get(topic.id)

                if not demand and not include_missing:
                    continue

                story.append(Paragraph(md_inline_to_rl(f"{idx}. {topic.name}"), styles["TopicTitle"]))

                meta_bits = [
                    f"Tier: <b>{topic.tier}</b>",
                    f"Weightage: <b>{topic.weightage}</b>",
                    f"Total Qs: <b>{topic.total_questions}</b>",
                ]
                if demand:
                    meta_bits += [
                        f"PYQs: <b>{demand.pyq_count}</b>",
                        f"Year span: <b>{(demand.year_span or '—')}</b>",
                        f"Model: <b>{(demand.model_used or '—')}</b>",
                        f"Updated: <b>{demand.updated_at.strftime('%Y-%m-%d %H:%M')}</b>",
                    ]
                else:
                    meta_bits.append("<b>No TopicDemand found for this topic.</b>")

                story.append(Paragraph(" • ".join(meta_bits), styles["Meta"]))

                if demand and demand.demand_insights:
                    story.extend(markdown_to_flowables(demand.demand_insights, styles))
                else:
                    story.append(Paragraph("No insights available.", styles["Body"]))
                    story.append(Spacer(1, 10))

                story.append(Spacer(1, 8))

            doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
            generated += 1
            self.stdout.write(self.style.SUCCESS(f"Generated: {outpath}"))

        self.stdout.write(self.style.SUCCESS(
            f"Done. PDFs generated: {generated}. Sections skipped: {skipped_sections}. Output dir: {outdir}"
        ))
