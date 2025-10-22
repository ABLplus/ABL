# syllabus/views_admin.py
from collections import defaultdict
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Count
from syllabus.models import Exam, Subject, Section, Topic
from question.models import Question
from syllabus.services.topic_weightage import recompute_topic_weightage_relative

START_YEAR = 2013
ONLY_PYQ = True


@staff_member_required
def topic_weight_view(request):
    exams = Exam.objects.order_by("name")
    selected_exam_id = request.GET.get("exam") or request.POST.get("exam")
    include_checked = request.POST.get("only_checked") == "on"

    context = {
        "exams": exams,
        "selected_exam_id": int(selected_exam_id) if selected_exam_id else None,
        "include_checked": include_checked,
        "data": [],
    }

    # Recalculate for a subject if requested
    if request.method == "POST" and request.POST.get("recalc_subject"):
        try:
            subj = Subject.objects.get(id=request.POST["recalc_subject"])
        except Subject.DoesNotExist:
            messages.error(request, "Subject not found.")
        else:
            recompute_topic_weightage_relative(subj, include_checked=include_checked)
            messages.success(
                request,
                f"Recalculated tiers for {subj.name} ({subj.exam.name}) using PYQs since {START_YEAR}"
                + (" (checked only)." if include_checked else ".")
            )

    if not selected_exam_id:
        return render(request, "syllabus/topic_weight.html", context)

    try:
        selected_exam = exams.get(id=selected_exam_id)
    except Exam.DoesNotExist:
        messages.error(request, "Exam not found.")
        return render(request, "syllabus/topic_weight.html", context)

    # Prefetch hierarchy
    subjects = (
        Subject.objects.filter(exam=selected_exam)
        .select_related("exam")
        .prefetch_related("sections__topics")
        .order_by("name")
    )

    # Build question filters
    qfilter = {"subject__exam": selected_exam, "year__gte": START_YEAR, "exam_name": selected_exam.name}
    if ONLY_PYQ:
        qfilter["source_type"] = "PYQ"
    if include_checked:
        qfilter["check_status"] = "checked"

    # Counts at each level
    per_subject = (
        Question.objects.filter(**qfilter)
        .values("subject_id")
        .annotate(n=Count("id"))
    )
    per_section = (
        Question.objects.filter(**qfilter, section__isnull=False)
        .values("section_id")
        .annotate(n=Count("id"))
    )
    per_topic = (
        Question.objects.filter(**qfilter, topic__isnull=False)
        .values("topic_id")
        .annotate(n=Count("id"))
    )

    subj_count = {r["subject_id"]: r["n"] for r in per_subject}
    sect_count = {r["section_id"]: r["n"] for r in per_section}
    topic_count = {r["topic_id"]: r["n"] for r in per_topic}

    # Structure for template
    data = []
    for s in subjects:
        sections_block = []
        for sec in s.sections.all().order_by("id"):
            topics_block = []
            for t in sec.topics.all().order_by("id"):
                topics_block.append({
                    "id": t.id,
                    "name": t.name,
                    "count": topic_count.get(t.id, 0),
                    "tier": t.tier if hasattr(t, "tier") else "never",
                    "weightage": getattr(t, "weightage", 0),
                })
            sections_block.append({
                "id": sec.id,
                "name": sec.name,
                "count": sect_count.get(sec.id, 0),
                "topics": topics_block,
            })
        data.append({
            "id": s.id,
            "name": s.name,
            "count": subj_count.get(s.id, 0),
            "sections": sections_block,
        })

    context["data"] = data
    return render(request, "syllabus/topic_weight.html", context)



TIER_CHOICES = [
    ("most", "Most Asked"),
    ("general", "Generally Asked"),
    ("rare", "Rarely Asked"),
    ("never", "Never Asked"),
]
DEFAULT_YEAR = 2013

@staff_member_required
def tier_questions_view(request):
    exams = Exam.objects.order_by("name")
    selected_exam_id = request.GET.get("exam")
    selected_tier = request.GET.get("tier") or "most"
    start_year = int(request.GET.get("year") or DEFAULT_YEAR)
    only_checked = request.GET.get("only_checked") == "on"
    only_pyq = request.GET.get("only_pyq", "on") == "on"  # default ON

    context = {
        "exams": exams,
        "tiers": TIER_CHOICES,
        "selected_exam_id": int(selected_exam_id) if selected_exam_id else None,
        "selected_tier": selected_tier,
        "start_year": start_year,
        "only_checked": only_checked,
        "only_pyq": only_pyq,
        "summary": None,
        "data": [],
    }

    if not selected_exam_id:
        return render(request, "syllabus/tier_questions.html", context)

    try:
        exam = exams.get(id=selected_exam_id)
    except Exam.DoesNotExist:
        return render(request, "syllabus/tier_questions.html", context)

    # Base question queryset (by year, PYQ, checked)
    base_q = Question.objects.filter(subject__exam=exam, year__gte=start_year, exam_name= exam.name)
    if only_pyq:
        base_q = base_q.filter(source_type="PYQ")
    if only_checked:
        base_q = base_q.filter(check_status="checked")
    total_questions = base_q.count()

    # All topics in the exam
    all_topics_qs = Topic.objects.filter(section__subject__exam=exam) \
                                 .select_related("section", "section__subject") \
                                 .order_by("section__subject__name", "section__id", "id")
    all_topic_ids = list(all_topics_qs.values_list("id", flat=True))
    total_topics_in_exam = len(all_topic_ids)

    # Counts per topic for the selected window
    per_topic_counts = (
        base_q.filter(topic_id__in=all_topic_ids)
              .values("topic_id")
              .annotate(n=Count("id"))
    )
    count_map = {row["topic_id"]: row["n"] for row in per_topic_counts}

    # Determine which topics are "in the selected tier"
    if selected_tier == "never":
        # dynamic: topics with 0 questions in the window
        topics_in_tier_ids = [tid for tid in all_topic_ids if count_map.get(tid, 0) == 0]
    else:
        # stored tier filter
        topics_in_tier_ids = list(
            all_topics_qs.filter(tier=selected_tier).values_list("id", flat=True)
        )

    topics_in_tier_count = len(topics_in_tier_ids)
    topics_in_tier_pct = round((topics_in_tier_count * 100 / total_topics_in_exam), 2) if total_topics_in_exam else 0.0

    # Tier question total = sum of counts for those topics (for "never" this should be 0)
    tier_questions = sum(count_map.get(tid, 0) for tid in topics_in_tier_ids)
    tier_questions_pct = round((tier_questions * 100 / total_questions), 2) if total_questions else 0.0

    # Build Subject → Sections → Topics (only those in selected tier, with counts)
    subjects = Subject.objects.filter(exam=exam).order_by("name").prefetch_related("sections__topics")
    data = []
    for s in subjects:
        secs_block = []
        subject_topics_all = [t for sec in s.sections.all() for t in sec.topics.all()]
        subject_total_topics = len(subject_topics_all)

        subject_tier_topics = []
        for sec in s.sections.all().order_by("id"):
            # topics under this section that match the tier
            if selected_tier == "never":
                tier_topics = [t for t in sec.topics.all() if count_map.get(t.id, 0) == 0]
            else:
                tier_topics = [t for t in sec.topics.all() if t.tier == selected_tier]

            if not tier_topics:
                continue

            topics_block = []
            for t in tier_topics:
                topics_block.append({
                    "id": t.id,
                    "name": t.name,
                    "count": count_map.get(t.id, 0),
                    "weightage": getattr(t, "weightage", 0),
                })
            secs_block.append({
                "id": sec.id,
                "name": sec.name,
                "topics": topics_block,
            })
            subject_tier_topics.extend(tier_topics)

        if secs_block:
            # per-subject tier topic % chip
            subj_tier_count = len(subject_tier_topics)
            subj_pct = round((subj_tier_count * 100 / subject_total_topics), 2) if subject_total_topics else 0.0
            data.append({
                "id": s.id,
                "name": s.name,
                "sections": secs_block,
                "subject_total_topics": subject_total_topics,
                "subject_tier_topics": subj_tier_count,
                "subject_tier_pct": subj_pct,
            })

    context["summary"] = {
        "exam_name": exam.name,
        "tier": selected_tier,
        "tier_label": dict(TIER_CHOICES).get(selected_tier, selected_tier.title()),
        "tier_questions": tier_questions,
        "total_questions": total_questions,
        "tier_questions_pct": tier_questions_pct,
        "topics_in_tier": topics_in_tier_count,
        "total_topics_in_exam": total_topics_in_exam,
        "topics_in_tier_pct": topics_in_tier_pct,
        "start_year": start_year,
    }
    context["data"] = data
    return render(request, "syllabus/tier_questions.html", context)
