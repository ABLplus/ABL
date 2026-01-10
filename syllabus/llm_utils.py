# # syllabus/llm_utils.py

# import os
# import re
# from typing import List, Literal, Optional, Dict, Any

# from openai import OpenAI
# from pydantic import BaseModel, Field


# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# # -------------------------
# # 1) Structured Output Schema
# # -------------------------

# DemandType = Literal["explicit", "implicit", "adjacent"]
# DemandTag = Literal["asked_frequently", "asked_occasionally", "adjacent_probable"]


# class Evidence(BaseModel):
#     question_ids: List[int] = Field(default_factory=list)
#     years: List[int] = Field(default_factory=list)
#     exams: List[str] = Field(default_factory=list)



# class SubtopicCandidate(BaseModel):
#     # sequence for study/presentation within the topic (1-based)
#     seq: int = Field(
#         ...,
#         ge=1,
#         le=999,
#         description="1-based order within its bucket/list"
#     )

#     label: str = Field(
#         ...,
#         min_length=3,
#         max_length=120,
#         description="Short reusable subtopic label"
#     )

#     type: DemandType
#     tag: DemandTag

#     # Optional importance score; useful later for UI sorting, weights, etc.
#     weight: int = Field(
#         50,
#         ge=0,
#         le=100,
#         description="Relative importance score"
#     )

#     evidence: Evidence = Field(default_factory=Evidence)

#     notes: Optional[str] = Field(
#         None,
#         max_length=280,
#         description="One-line rationale, pattern-level only"
#     )


# class TopicDemandMap(BaseModel):
#     topic_id: int
#     topic_path: str
#     pyq_count: int
#     approx_year_span: str

#     # Ordered lists (seq must be unique within each list)
#     explicit_subtopics: List[SubtopicCandidate] = Field(default_factory=list)
#     implicit_concepts: List[SubtopicCandidate] = Field(default_factory=list)
#     adjacent_subtopics: List[SubtopicCandidate] = Field(default_factory=list)

#     # Traceability
#     source_exams_used: List[str] = Field(default_factory=list)


# # -------------------------
# # 2) Prompts
# # -------------------------

# SYSTEM_PROMPT_DEMAND_MAP = """
# You are an expert UPSC exam analyst.

# Task:
# Given a Topic Path and a list of PYQs from UPSC-run exams (CSE Prelims, CAPF, CDS) mapped to that topic,
# produce a TopicDemandMap that matches the provided schema exactly.

# What you must do:
# 1) Identify explicit subtopics tested (visible from the given PYQs).
# 2) Identify implicit concepts required (prerequisites needed to solve these PYQs).
# 3) Identify adjacent subtopics (logically connected areas that could be asked next; not necessarily present in this PYQ set).
# 4) Assign a tag to each candidate:
#    - asked_frequently
#    - asked_occasionally
#    - adjacent_probable
# 5) Assign seq (1-based) inside each list, representing a sensible study order:
#    - prerequisites first,
#    - then the core subtopics asked,
#    - then adjacent expansions.

# Strict rules:
# - Subtopics must be derived from patterns in the given PYQs. Do not import external syllabus lists.
# - Keep labels short and reusable. Merge duplicates/synonyms.
# - Do NOT quote full question text/options. Notes must be pattern-level.
# - Evidence must cite question_ids where possible.
# - If PYQs are too few for confident splitting, keep the map small and say so in notes.

# Return ONLY a response that conforms to the schema.
# """.strip()


# # -------------------------
# # 3) Helpers (optional but recommended)
# # -------------------------

# def _basic_clean_text(text: str) -> str:
#     """Light cleanup to reduce noise before sending to LLM."""
#     if not text:
#         return ""
#     text = re.sub(r"\s+", " ", text).strip()
#     return text


# def _build_year_span(pyq_list: List[Dict[str, Any]]) -> str:
#     years = sorted({q.get("year") for q in pyq_list if q.get("year")})
#     if not years:
#         return "Not clear from data"
#     return f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])


# def _normalize_exam_name(exam: str) -> str:
#     """Keep exam labels clean and consistent for traceability."""
#     exam = (exam or "").strip()
#     # You can map your internal names here if needed
#     # e.g. "CSE Prelims" / "CAPF" / "CDS"
#     return exam or "Unknown"


# def _post_tag_by_evidence(candidate: SubtopicCandidate) -> DemandTag:
#     """
#     Deterministic tag rule to prevent drift:
#     - explicit/implicit: based on evidence count (question_ids)
#     - adjacent: always adjacent_probable
#     """
#     if candidate.type == "adjacent":
#         return "adjacent_probable"

#     n = len(set(candidate.evidence.question_ids or []))
#     if n >= 4:
#         return "asked_frequently"
#     if n >= 2:
#         return "asked_occasionally"
#     # If explicit/implicit but only 0-1 evidence, keep it occasional (still better than hallucinated frequency)
#     return "asked_occasionally"


# def stabilize_map(dmap: TopicDemandMap, override_tags: bool = True) -> TopicDemandMap:
#     """
#     Optional cleanup:
#     - enforce tag deterministically from evidence (recommended)
#     - sort each list by seq
#     """
#     def sort_and_fix(items: List[SubtopicCandidate]) -> List[SubtopicCandidate]:
#         items = sorted(items, key=lambda x: x.seq)
#         if override_tags:
#             for it in items:
#                 it.tag = _post_tag_by_evidence(it)
#         return items

#     dmap.explicit_subtopics = sort_and_fix(dmap.explicit_subtopics)
#     dmap.implicit_concepts = sort_and_fix(dmap.implicit_concepts)
#     dmap.adjacent_subtopics = sort_and_fix(dmap.adjacent_subtopics)

#     return dmap


# # -------------------------
# # 4) Main function: Demand Map (Structured Output)
# # -------------------------

# def analyze_topic_demand_map(
#     topic_id: int,
#     topic_path: str,
#     pyq_list: List[Dict[str, Any]],
#     model_name: str = "gpt-4o-2024-08-06",
#     temperature: float = 0.2,
#     override_tags: bool = True,
# ) -> Optional[TopicDemandMap]:
#     """
#     Given a topic and its PYQs, returns a structured TopicDemandMap.

#     Expected pyq_list item format (minimum):
#       {
#         "id": 123,
#         "year": 2020,
#         "exam_name": "CSE Prelims" | "CAPF" | "CDS",
#         "question": "...",          # can be question_html stripped to text
#         # optional:
#         "options": ["A...", "B...", "C...", "D..."],
#         "answer": "C",              # optional
#         "explanation": "...",       # optional
#       }

#     Note:
#     - It's OK to send the question text; the rule is about NOT QUOTING it in output.
#     """

#     if not pyq_list:
#         return None

#     year_span = _build_year_span(pyq_list)

#     # Minify + sanitize what we send
#     compact_pyqs = []
#     source_exams = set()

#     for q in pyq_list:
#         qid = q.get("id")
#         if qid is None:
#             continue

#         exam = _normalize_exam_name(q.get("exam_name") or q.get("exam") or "")
#         source_exams.add(exam)

#         compact_pyqs.append({
#             "id": int(qid),
#             "year": q.get("year"),
#             "exam_name": exam,
#             "question": _basic_clean_text(q.get("question") or q.get("question_text") or q.get("question_html") or ""),
#             # keep options optional (sometimes useful for “traps” inference)
#             "options": q.get("options"),
#         })

#     user_payload = {
#         "topic_id": topic_id,
#         "topic_path": topic_path,
#         "pyq_count": len(compact_pyqs),
#         "approx_year_span": year_span,
#         "source_exams_used": sorted(source_exams),
#         "pyq_list": compact_pyqs,
#     }

#     # Responses API + parse into Pydantic (Structured Outputs) :contentReference[oaicite:1]{index=1}
#     resp = client.responses.parse(
#         model=model_name,
#         instructions=SYSTEM_PROMPT_DEMAND_MAP,
#         input=[{"role": "user", "content": user_payload}],
#         text_format=TopicDemandMap,
#         temperature=temperature,
#     )

#     dmap: TopicDemandMap = resp.output_parsed

#     # Optional stability enforcement (recommended for production)
#     dmap = stabilize_map(dmap, override_tags=override_tags)
#     return dmap














































#  syllabus/llm_utils.py

import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an expert UPSC exam analyst.

TASK
Given:
- A Topic Path
- A list of PYQs from UPSC-run exams (CSE Prelims, CAPF, CDS) mapped to that topic

Produce a **TopicDemandMap** that conforms EXACTLY to the required schema and structure.

────────────────────────
WHAT YOU MUST DO
────────────────────────
1. Identify **explicit subtopics actually tested** in the given PYQs.
   - Each subtopic must be backed by evidence using `question_ids`.

2. Arrange subtopics in a **logical study sequence** (foundational → advanced).

3. Identify **implicit concepts / prerequisites** required to solve these PYQs
   (even if not directly asked).

4. Identify **adjacent subtopics**
   - Closely related areas UPSC could logically ask next
   - These may NOT appear in the current PYQs.
5. List down the type of demand for each subtopic. Which facts, concepts, or application it test.

────────────────────────
STRICT RULES (NON-NEGOTIABLE)
────────────────────────
- Subtopics MUST be derived only from patterns in the given PYQs.
  ❌ Do NOT import external syllabus lists or textbook headings.

- A `question_id` may appear in the evidence of **ONLY ONE** subtopic.

- Keep subtopic labels:
  - Short
  - Conceptual
  - Reusable
  - Merge synonyms or overlapping ideas.

- Do NOT:
  - Quote full question text
  - Quote options
  - Reproduce PYQs verbatim

- Notes must remain **pattern-level**, not question-level.

- If the PYQ count is too small for confident subdivision:
  - Keep the map minimal
  - Explicitly state this limitation in notes.

────────────────────────
OUTPUT FORMAT (MANDATORY)
────────────────────────
- Return **ONLY** the TopicDemandMap.
- Output must be **GitHub-flavored Markdown**.
- Use clean hierarchy ONLY:
  - `#` for the main title
  - `##` for major sections
  - `###` for subtopics

- Use:
  - Bullet lists
  - Short, precise paragraphs

- ❌ No random formatting
- ❌ No emojis
- ❌ No tables
- ❌ No code blocks unless absolutely unavoidable

- Each subtopic must appear under a clear heading.
- Each section must be clearly labeled.

The response MUST strictly conform to the schema and formatting rules above.

"""

def analyze_topic_with_llm(topic_path: str, pyq_list: list, model_name: str = "gpt-5-nano") -> str:
    """
    Given a topic_path and list of PYQs, call the LLM and return
    a nuanced Markdown 'Topic Demand Report'.

    model_name can be switched to experiment with different models.
    """

    if not pyq_list:
        return f"# Topic Demand Report: {topic_path}\n\n_No PYQs found for this topic (CSE Prelims / PYQ source)._"

    years = sorted({q.get("year") for q in pyq_list if q.get("year")})
    if years:
        year_span = f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])
    else:
        year_span = "Not clear from data"

    user_payload = {
        "topic_path": topic_path,
        "exam_name": "UPSC Civil Services (Preliminary) Examination",
        "pyq_count": len(pyq_list),
        "approx_year_span": year_span,
        "pyq_list": pyq_list,
    }

    user_json = json.dumps(user_payload, ensure_ascii=False, indent=2)


    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "You are given the topic path and a list of PYQs for this topic.\n"
                    "Write a detailed Topic Demand Report in MARKDOWN following the exact structure described.\n\n"
                    "Here is the data (JSON):\n\n"
                    f"```json\n{user_json}\n```"
                ),
            },
        ],
        temperature=0.25,
    )

    markdown_report = response.choices[0].message.content
    return markdown_report
