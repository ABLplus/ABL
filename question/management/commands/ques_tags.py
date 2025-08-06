from django.core.management.base import BaseCommand
from django.db.models import Q
from question.models import OLT
from syllabus.models import Subject, Section, Topic, Ques
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict
import json, os, re, time

# ─────────────────────────────────────────── NEW: 11 one-liner rules
OLT_RULES = {
    "OLT-01": "4 stand-alone options (A–D); single correct.",
    "OLT-02": "2 statements; options: 1 only / 2 only / both / neither.",
    "OLT-03": "3+ statements; options list combination codes (1-3, 2-3, etc.).",
    "OLT-04": "Match List-I ↔ List-II; choose correct matching code.",
    "OLT-05": "Several pairs; ask how many pairs are correctly matched.",
    "OLT-06": "Assertion (A) + Reason (R); pick one of 4 classic A/R codes.",
    "OLT-07": "Statement I with explanations II & III; judge which explain/correct.",
    "OLT-08": "Statement I & II; judge correctness and if II explains I.",
    "OLT-09": "List of 4–6 items; options offer different valid subsets.",
    "OLT-10": "Visual / map / diagram; answer by interpreting the image.",
    "OLT-11": "Arrange items in correct chronological / logical sequence.",
}
# ──────────────────────────────────────────────────────────────────

THROTTLE_SEC = 0.1          # set 0 to disable throttling

def build_topic_list(section: Section) -> list[str]:
    """Alphabetically-sorted topic names inside one section."""
    return list(
        Topic.objects.filter(section=section)
             .order_by("name")
             .values_list("name", flat=True)
    )

class Command(BaseCommand):
    help = "Tag Topic, OLT & Explanation for all questions (Subject → Section loop)"

    def handle(self, *args, **kwargs):
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        stats = defaultdict(lambda: {"ok": 0, "err": 0})

        for subj in Subject.objects.all():
            print(f"\n📚 Subject: {subj.name}")

            for sec in Section.objects.filter(subject=subj).order_by("name"):

                topics = build_topic_list(sec)
                if not topics:
                    continue

                qs = (
                    Ques.objects
                            .filter(subject=subj, section=sec).filter(topic__isnull=True)     # CHANGED: filter untagged questions                         
                )
                total = qs.count()
                if not qs.exists():
                    print("  ▸ No questions — skipping.")
                    continue

                print(f"  ▶ Section: {sec.name} — {total} untagged")
                menu = "\n".join(f"- {t}" for t in topics)
                print(menu)
                olt_menu = json.dumps(OLT_RULES, separators=(",", ":"))  # CHANGED: compact JSON

                for idx, q in enumerate(qs, 1):
                    print(f"    [{idx}/{total}] Q{q.id}")

                    # ───────────────────────── prompt
                    system_prompt = f"""
You are a UPSC MCQ-tagging expert.

Step 1 – Topic  
Pick **one** topic from the list below *exactly as written*:
{menu}

Avoid using any topic not in the list and do not create new topics. Choose the most relevant topic that best fits the question and options.

Step 2 – OLT code  
Choose the correct OLT code from this map (key → rule):  
{olt_menu}

Step 3 – Explanation  
Be brief, accurate, and use only information relevant to the question. preference 150 words and Maximum 300 words.Don't repeat the full question or options. Just focus on reasoning and clarity. If deem fit, at last provide a concept note for the main topic of the question in additional 100 words.

Give the explanation in markdown format.Include line breaks. Include headings for Correct option, why correct, and why others incorrect. Use bullet points for clarity.

Return **only** this JSON:
{{
  "topic_name": "...",
  "olt_type": "...",          # e.g. "OLT-02"
  "updated_explanation": "..."
}}
""".strip()

                    user_prompt = f"""
MCQ:
Q: {q.q_markdown}
A. {q.a}
B. {q.b}
C. {q.c}
D. {q.d}

Correct Option: {q.correct_option}
""".strip()

                    try:
                        resp = client.chat.completions.create(
                            model="gpt-4o-mini",
                            response_format={"type": "json_object"},
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user",   "content": user_prompt},
                            ],
                            temperature=0.3,
                        )
                        result = json.loads(resp.choices[0].message.content)

                        # ---------- topic resolve
                        topic_name = result["topic_name"].strip()
                        if topic_name not in topics:
                            raise ValueError(f"Topic '{topic_name}' not in list.")
                        topic_obj = Topic.objects.filter(name=topic_name, section=sec).first()
                        if not topic_obj:
                            raise ValueError(f"Topic '{topic_name}' not found in DB.")

                        # ---------- OLT resolve
                        m = re.search(r"OLT-\d{2}", result["olt_type"])
                        olt_code = m.group(0) if m else None
                        olt_obj  = OLT.objects.filter(code=olt_code).first()
                        if not olt_obj:
                            raise ValueError(f"OLT '{olt_code}' not found.")

                        # ---------- persist
                        q.topic = topic_obj
                        q.topic_name = topic_name
                        q.olt   = olt_obj
                        q.olt_type = olt_code
                        q.exp_generated = result["updated_explanation"]
                        q.save()

                        stats[subj.name]["ok"] += 1
                        print("        ✅ saved")
                        time.sleep(THROTTLE_SEC)

                    except Exception as exc:
                        stats[subj.name]["err"] += 1
                        print(f"        ❌ {exc}")

        # ---------------- summary
        print("\n============= RUN SUMMARY =============")
        total_ok = total_err = 0
        for name, s in stats.items():
            total_ok  += s["ok"]
            total_err += s["err"]
            print(f"• {name:<25} Success {s['ok']:<3} | Errors {s['err']}")
        print("---------------------------------------")
        print(f"TOTAL  |  Success {total_ok}   Errors {total_err}")
        print("COMPLETE ✅" if total_err == 0 else "COMPLETE ⚠ (with errors)")
