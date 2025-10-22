# analysis/services/topic_weightage.py
from django.db import transaction
from django.db.models import Count
from question.models import Question
from syllabus.models import Subject, Topic

START_YEAR = 2013
ONLY_PYQ = True
ONLY_CHECKED = False  # set True if you only want "checked" questions


def _relative_tiers(count_map, topic_ids):
    """
    Returns {topic_id: tier_str} where tier ∈ {'most','asked','rare','never'}.
    Top 25% of nonzero counts → 'most'
    Middle 50% → 'asked'
    Bottom 25% → 'rare'
    Zero-count → 'never'
    """
    nz = [(tid, c) for tid, c in count_map.items() if c > 0]
    nz.sort(key=lambda x: x[1], reverse=True)
    n = len(nz)

    tiers = {}
    if n:
        for idx, (tid, _) in enumerate(nz, start=1):
            p = idx / n
            if p <= 0.25:
                tiers[tid] = "most"
            elif p <= 0.75:
                tiers[tid] = "asked"
            else:
                tiers[tid] = "rare"

    # zero → never
    for tid in topic_ids:
        if count_map.get(tid, 0) == 0:
            tiers[tid] = "never"
    return tiers


@transaction.atomic
def recompute_topic_weightage_relative(subject: Subject, include_checked=ONLY_CHECKED):
    """
    Computes and saves Topic.weightage & Topic.tier for a given subject.
    Weightage = 100 * topic_question_count / total_questions_in_subject (since 2013)
    Tier = relative band within subject:
       Top 25% → Most
       Middle 50% → Asked
       Bottom 25% → Rare
       Zero-count → Never
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

    # Compute relative tiers
    tiers = _relative_tiers(count_map, topic_ids)

    # Update each topic’s weightage & tier
    for t in topics:
        cnt = count_map.get(t.id, 0)
        t.weightage = round(100.0 * cnt / subject_total, 3) if subject_total else 0.0
        t.tier = tiers.get(t.id, "never")

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
    order_key = {"most": 0, "general": 1, "rare": 2, "never": 3}
    rows.sort(key=lambda r: (order_key.get(r["tier"], 9), -r["count"], r["section"], r["topic"]))

    return {
        "subject_total": subject_total,
        "rows": rows,
        "topics_updated": len(topics),
    }
