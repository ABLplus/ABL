# syllabus/views_admin.py
from collections import defaultdict
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db.models import Count
from syllabus.models import Exam, Subject, Section, Topic
from question.models import Question
from analysis.services.topic_weightage import recompute_topic_weightage_relative

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
    qfilter = {"subject__exam": selected_exam, "year__gte": START_YEAR}
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
