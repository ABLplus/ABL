from django.core.management.base import BaseCommand
from question.models import Question, OLT            # adjust path if different
from syllabus.models import Subject, Section, Topic
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict
import json, os, time
from utils.olt_types import OLT_TYPE_JSON
from django.db.models import Q     

from utils.olt_llm_rules import LLM_RULES           # custom, LLM-friendly rules


def build_topic_list(subject: Subject) -> list[str]:
    """
    Returns a plain list of topic names for a given subject,
    sorted alphabetically.
    """
    topics = (
        Topic.objects
             .filter(section__subject=subject)    # traverse FK from Topic → Section → Subject
             .order_by("name")
             .values_list("name", flat=True)
    )
    return list(topics)

# ──────────────────────────────────────────────────────────────────────────────
#  Management Command
# ──────────────────────────────────────────────────────────────────────────────
class Command(BaseCommand):
    help = "Auto-tag Section, Topic, OLT & Explanation for ALL subjects (unit=8)"

    def handle(self, *args, **kwargs):
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        stats = defaultdict(lambda: {"ok": 0, "err": 0})

        for subj in Subject.objects.all():
            print(f"\n📚 Subject: {subj.name}")            
            topic_list = build_topic_list(subj)

            qs = (Question.objects
            .filter(subject=subj)                # current subject
            .filter(explanation_generated__isnull=True)   # only untagged
            )

            if not qs.exists():
                print("  ▸ No questions — skipping.")
                continue
            

            for idx, q in enumerate(qs, 1):
                print(f"  [{idx}/{qs.count()}] Q{q.id}")                

                # ── Build prompts ───────────────────────────────────────────
                system_prompt = f"""
You are an expert in UPSC MCQ tagging and explanation.

1. On the basis of the given MCQ, choose the most appropriate topic from the list: {json.dumps(topic_list)}. Avoid using any topic not in the list and do not create new topics. Choose the most relevant topic that best fits the question and options. RETURN ONLY THE TOPIC NAME as *given in the list*, without any additional characters.


2. Identify the Option Layout Type (OLT) based on this schema:
{json.dumps(OLT_TYPE_JSON)}


3. "olt_type" output shold be one of the keys from OLT_TYPE_JSON i.e. the OLT code such as OLT-01,OLT-02 etc.

4.Be brief, accurate, and use only information relevant to the question. preference 150 words and Maximum 300 words.Don't repeat the full question or options. Just focus on reasoning and clarity. If deem fit, at last provide a concept note for the main topic of the question in additional 100 words.

5. Give the explanation in markdown format.Include line breaks. Include headings for Correct option, why correct, and why others incorrect. Use bullet points for clarity.


Return a valid JSON:
{{
  "topic_name": "...",
  "olt_type": "...",
  "updated_explanation": "..."
}}
""".strip()

                user_prompt = f"""
MCQ:
Q: {q.question_html}
A. {q.option_a}
B. {q.option_b}
C. {q.option_c}
D. {q.option_d}

Correct Option: {q.correct_option}
""".strip()
                # ── Call OpenAI ─────────────────────────────────────────────
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.3,
                    )
                    result = json.loads(resp.choices[0].message.content)

                    # ── Resolve FKs ────────────────────────────────────────
                    topic_name= result["topic_name"].strip()
                    if topic_name not in topic_list:
                        raise ValueError(f"Topic '{topic_name}' not in list.")
                    else:
                        # use .filter().first() to avoid DoesNotExist / MultipleObjectsReturned
                        topic_obj = (
                            Topic.objects
                                .filter(name=topic_name, section__subject=subj)
                                .first()
                        )
                        q.topic = topic_obj
                        if not topic_obj:                       # still None?  DB mismatch
                            raise ValueError(f"Topic '{topic_name}' not found in DB.")


                    # keep only the pure code part, in case model still appends text
                    olt_code   = result["olt_type"].split()[0]    # ⬅
                   

                   

                    # ── Persist ───────────────────────────────────────────
                    q.topic_name = topic_name
                    
                    
                    q.olt_type = olt_code
                    olt_obj  = (OLT.objects
                                    .filter(Q(code=olt_code) | Q(name=olt_code))
                                    .first())
                    if olt_obj:
                        q.olt = olt_obj
                    else:
                        raise ValueError(f"OLT '{olt_code}' not found.")

                        
                    q.explanation_generated = result["updated_explanation"]
                    q.save()

                    stats[subj.name]["ok"] += 1
                    print("      ✅ saved")
                    

                except Exception as exc:
                    stats[subj.name]["err"] += 1
                    print(f"      ❌ {exc}")

        # ── Final Summary ──────────────────────────────────────────────────
        print("\n================  RUN SUMMARY  ================")
        total_ok = total_err = 0
        for name, s in stats.items():
            total_ok += s["ok"]
            total_err += s["err"]
            print(f"• {name:<30}  Success: {s['ok']:<4}  Errors: {s['err']}")
        print("----------------------------------------------")
        print(f"TOTAL  |  Success: {total_ok}   Errors: {total_err}")
        print("COMPLETE ✅" if total_err == 0 else "COMPLETE ⚠ (with errors)")
