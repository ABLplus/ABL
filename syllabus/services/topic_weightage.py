# analysis/services/topic_weightage.py
from __future__ import annotations

from django.db import transaction
from django.db.models import Count
from question.models import Question
from syllabus.models import Subject, Topic

START_YEAR = 2013
ONLY_PYQ = True
ONLY_CHECKED = False  # set True if you only want "checked" questions


def _tier3_cumulative_share(
    count_map: dict[int, int],
    topic_ids: list[int],
    *,
    tier1_cut: float = 0.60,
    tier2_cut: float = 0.90,
) -> dict[int, str]:
    """
    Returns {topic_id: tier_str} where tier ∈ {'tier1','tier2','tier3'}.

    Method: cumulative-share (Pareto-friendly)
    - Consider only topics with count > 0 to build the demand curve.
    - Sort by (count desc, topic_id asc) for deterministic tiers.
    - Compute cumulative share over total counts (non-zero topics).
      * cum <= 0.60  -> tier1
      * cum <= 0.90  -> tier2
      * else         -> tier3
    - Zero-count topics are always tier3.

    Notes:
    - If total non-zero questions == 0, all topics become tier3.
    - Ties are stable due to topic_id tie-break.
    """
    # Build non-zero list (topic_id, count)
    nz = [(tid, c) for tid, c in count_map.items() if c > 0]

    # Deterministic ordering: count desc, topic_id asc
    nz.sort(key=lambda x: (-x[1], x[0]))

    tiers: dict[int, str] = {}

    total_nz = sum(c for _, c in nz)
    if total_nz > 0:
        running = 0
        for tid, c in nz:
            running += c
            cum = running / total_nz
            if cum <= tier1_cut:
                tiers[tid] = "tier1"
            elif cum <= tier2_cut:
                tiers[tid] = "tier2"
            else:
                tiers[tid] = "tier3"

    # Zero-count (or missing) -> tier3
    for tid in topic_ids:
        if count_map.get(tid, 0) == 0:
            tiers[tid] = "tier3"

    return tiers


@transaction.atomic
def recompute_topic_weightage_relative(subject: Subject, include_checked=ONLY_CHECKED):
    """
    Computes and saves Topic.weightage & Topic.tier for a given subject.

    Weightage:
        100 * topic_question_count / total_questions_in_subject (since START_YEAR)

    Tiering (3 tiers):
        tier1/tier2/tier3 using cumulative-share over non-zero topic counts:
          - tier1: first ~60% of questions
          - tier2: next ~30% (up to ~90%)
          - tier3: remaining tail + zero-count topics

    Returns: dict with summary data for UI.
    """
    # Base filter
    qfilter = {"subject": subject, "year__gte": START_YEAR, "exam_name": subject.exam.name}
    if ONLY_PYQ:
        qfilter["source_type"] = "PYQ"
    if include_checked:
        qfilter["check_status"] = "checked"

    # Count total PYQs for the subject
    subject_total = Question.objects.filter(**qfilter).count()

    # Per-topic question counts
    per_topic = (
        Question.objects.filter(**qfilter, topic__isnull=False)
        .values("topic")
        .annotate(n=Count("id"))
    )
    count_map = {row["topic"]: row["n"] for row in per_topic}

    # Get all topics of this subject
    topics = list(
        Topic.objects.filter(section__subject=subject)
        .select_related("section")
        .order_by("id")
    )
    topic_ids = [t.id for t in topics]

    # Compute 3-tier demand tiers
    tiers = _tier3_cumulative_share(count_map, topic_ids, tier1_cut=0.60, tier2_cut=0.90)

    # Update each topic’s weightage & tier
    for t in topics:
        cnt = count_map.get(t.id, 0)
        t.weightage = round(100.0 * cnt / subject_total, 3) if subject_total else 0.0
        t.tier = tiers.get(t.id, "tier3")

    # Bulk save to DB
    if topics:
        Topic.objects.bulk_update(topics, ["weightage", "tier"])

    # Prepare summary for display
    rows = []
    for t in topics:
        rows.append({
            "topic_id": t.id,
            "section": t.section.name,
            "topic": t.name,
            "count": count_map.get(t.id, 0),
            "weightage": t.weightage,
            "tier": t.tier,
        })

    # Sort for UI
    order_key = {"tier1": 0, "tier2": 1, "tier3": 2}
    rows.sort(key=lambda r: (order_key.get(r["tier"], 9), -r["count"], r["section"], r["topic"]))

    return {
        "subject_total": subject_total,
        "rows": rows,
        "topics_updated": len(topics),
    }
