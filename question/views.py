
from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from syllabus.models import *
from .forms import QuestionForm, QuestionRowForm
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Count, Q
from collections import defaultdict
from django.utils.http import urlencode


STATUSES = ("pending", "review", "checked")

def _blank_counts():
    return {s: 0 for s in STATUSES} | {"total": 0}

@staff_member_required
def questions_check_status_tree(request):
    """
    Hierarchical dashboard:
      Subject -> Section -> Topic
    Counts by check_status at each level, with filters (exam, year, source, subject).
    """
    qs = Question.objects.select_related("subject", "section", "topic")

    # ---- Filters ----
    exam    = request.GET.get("exam") or None
    year    = request.GET.get("year") or None
    source  = request.GET.get("source") or None
    subject = request.GET.get("subject") or None
    section = request.GET.get("section") or None  # optional carry-through (not used to filter)

    if exam:
        qs = qs.filter(exam_name=exam)
    if year:
        qs = qs.filter(year=year)
    if source:
        qs = qs.filter(source_type=source)
    if subject:
        qs = qs.filter(subject_id=subject)

    # ---- Grouped rows ----
    subj_rows = qs.values("subject_id", "subject__name", "check_status").annotate(cnt=Count("id"))
    sect_rows = qs.values("subject_id", "subject__name",
                          "section_id", "section__name",
                          "check_status").annotate(cnt=Count("id"))
    topic_rows = qs.values("subject_id", "subject__name",
                           "section_id", "section__name",
                           "topic_id", "topic__name",
                           "check_status").annotate(cnt=Count("id"))

    # ---- Build tree ----
    tree = defaultdict(lambda: {
        "name": None,
        "counts": _blank_counts(),
        "sections": defaultdict(lambda: {
            "name": None,
            "counts": _blank_counts(),
            "topics": defaultdict(lambda: {
                "name": None,
                "counts": _blank_counts()
            })
        })
    })

    # Subject counts
    for r in subj_rows:
        sid = r["subject_id"]
        sname = r["subject__name"] or "(Unassigned)"
        status = r["check_status"] or "pending"
        cnt = r["cnt"] or 0
        node = tree[sid]
        node["name"] = sname
        node["counts"][status] += cnt
        node["counts"]["total"] += cnt

    # Section counts
    for r in sect_rows:
        sid = r["subject_id"]; secid = r["section_id"]
        sname = r["subject__name"] or "(Unassigned)"
        secname = r["section__name"] or "(Unassigned)"
        status = r["check_status"] or "pending"
        cnt = r["cnt"] or 0

        snode = tree[sid]
        snode["name"] = snode["name"] or sname
        secnode = snode["sections"][secid]
        secnode["name"] = secname
        secnode["counts"][status] += cnt
        secnode["counts"]["total"] += cnt

    # Topic counts
    for r in topic_rows:
        sid = r["subject_id"]; secid = r["section_id"]; tid = r["topic_id"]
        sname = r["subject__name"] or "(Unassigned)"
        secname = r["section__name"] or "(Unassigned)"
        tname = r["topic__name"] or "(Unassigned)"
        status = r["check_status"] or "pending"
        cnt = r["cnt"] or 0

        snode = tree[sid]
        snode["name"] = snode["name"] or sname
        secnode = snode["sections"][secid]
        secnode["name"] = secnode["name"] or secname
        tnode = secnode["topics"][tid]
        tnode["name"] = tname
        tnode["counts"][status] += cnt
        tnode["counts"]["total"] += cnt

    # ---- Sort & convert to lists; compute % and topic flags ----
    def sort_key_name(x):  # x is (id, node)
        _id, node = x
        nm = node["name"] or ""
        return (nm == "(Unassigned)", nm.lower())

    subjects_out = []
    for sid, snode in sorted(tree.items(), key=sort_key_name):
        # Subject % checked
        s_total   = snode["counts"]["total"] or 0
        s_checked = snode["counts"]["checked"] or 0
        s_pct     = int(round((s_checked * 100.0) / s_total)) if s_total > 0 else 0
        s_done    = (s_total > 0 and s_checked == s_total)

        sections_out = []
        for secid, secnode in sorted(snode["sections"].items(), key=sort_key_name):
            sec_total   = secnode["counts"]["total"] or 0
            sec_checked = secnode["counts"]["checked"] or 0
            sec_pct     = int(round((sec_checked * 100.0) / sec_total)) if sec_total > 0 else 0
            sec_done    = (sec_total > 0 and sec_checked == sec_total)

            topics_out = []
            for tid, tnode in sorted(secnode["topics"].items(), key=sort_key_name):
                t_total   = tnode["counts"]["total"] or 0
                t_checked = tnode["counts"]["checked"] or 0
                t_pct     = int(round((t_checked * 100.0) / t_total)) if t_total > 0 else 0
                t_done    = (t_total > 0 and t_checked == t_total)

                topics_out.append({
                    "id": tid,
                    **tnode,
                    "pct_checked": t_pct,     # optional for future UI
                    "is_complete": t_done,    # for green topic name
                })

            sections_out.append({
                "id": secid,
                **secnode,
                "topics": topics_out,
                "pct_checked": sec_pct,      # for progress bar
                "is_complete": sec_done,
            })

        subjects_out.append({
            "id": sid,
            **snode,
            "sections": sections_out,
            "pct_checked": s_pct,           # for progress bar
            "is_complete": s_done,
        })

    # ---- Filter choices ----
    exams = (Question.objects.exclude(exam_name__isnull=True)
             .values_list("exam_name", flat=True).distinct().order_by("exam_name"))
    years = (Question.objects.exclude(year__isnull=True)
             .values_list("year", flat=True).distinct().order_by("year"))
    sources = ["PYQ", "AI"]
    all_subjects = Subject.objects.order_by("name")

    # ---- Carry base (excludes topic/status so topic pills can set them) ----
    carry_base = urlencode({
        k: v for k, v in {
            "exam": exam,
            "year": year,
            "source": source,
            "subject": subject,
            "section": section,  # include if you want to persist section selection
        }.items() if v
    })

    return render(
        request,
        "question/Questions-Check-status.html",
        {
            "subjects": subjects_out,
            "filters": {"exam": exam, "year": year, "source": source, "subject": subject},
            "exams": exams,
            "years": years,
            "sources": sources,
            "all_subjects": all_subjects,
            "STATUSES": STATUSES,
            "carry_base": carry_base,  # use this in topic pill links
        },
    )

@staff_member_required
def question_summary(request):
    """
    List CSE-Prelims exams (2000-2025) and show how many questions in that
    exam-year are pending / under-review / checked.
    Clicking a number jumps to question_list with ?exam=&year=&status=
    """

    EXAM_NAME = "CSE Prelims"

    # limit to the required exam and year range
    qs = Question.objects.filter(
        exam_name=EXAM_NAME,
        year__gte=2000,
        year__lte=2025,
    )

    rows = (
        qs.values("year")
           .annotate(
               pending=Count("id", filter=Q(check_status="pending")),
               review=Count("id",  filter=Q(check_status="review")),
               checked=Count("id", filter=Q(check_status="checked")),
           )
           .order_by("-year")      # newest year first
    )

    return render(
        request,
        "question/question_summary.html",
        {"exam_name": EXAM_NAME, "rows": rows},
    )


def subject_summary(request):
    subjects = Subject.objects.annotate(
        total   = Count('questions'),
        pending = Count('questions', filter=Q(questions__check_status='pending')),
        review  = Count('questions', filter=Q(questions__check_status='review')),
        checked = Count('questions', filter=Q(questions__check_status='checked')),
    )

    nosub = Question.objects.filter(subject__isnull=True).aggregate(
        total   = Count('id'),
        pending = Count('id', filter=Q(check_status='pending')),
        review  = Count('id', filter=Q(check_status='review')),
        checked = Count('id', filter=Q(check_status='checked')),
    )

    return render(request, 'question/subject_summary.html', {
        'subjects': subjects,
        'nosub':    nosub,
    })

# Add (Create) View
@staff_member_required
def add_question(request):
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('question:question_list')
    else:
        form = QuestionForm()
    return render(request, 'question/add_question.html', {'form': form})

# Edit (Update) View
@staff_member_required
def edit_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            return redirect('question:question_list')
    else:
        form = QuestionForm(instance=question)
    return render(request, 'question/edit_question.html', {'form': form, 'question': question})

# Delete View
@staff_member_required
def delete_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if request.method == 'POST':
        question.delete()
        return redirect('question_list')
    return render(request, 'question/delete_question.html', {'question': question})

# List View (to view all questions)
@staff_member_required
def question_list(request):
    qs = Question.objects.all().order_by("-created_at")
    

    # 1. Gather filter params
    exam        = request.GET.get("exam")
    year        = request.GET.get("year")
    subject_id  = request.GET.get("subject")
    section_id  = request.GET.get("section")
    topic_id    = request.GET.get("topic")
    subtopic_id = request.GET.get("subtopic")
    olt_code    = request.GET.get("olt")
    check_status = request.GET.get("status")


    # 2. Apply filters

    # Apply exam filter
    if exam:
        if exam == "none":
            qs = qs.filter(exam_name__isnull=True)
        else:
            qs = qs.filter(exam_name=exam)

    if year:
        if year == "none":
            qs = qs.filter(year__isnull=True)
        else:
            qs = qs.filter(year=year)

    if subject_id:
        if subject_id == "none":
            qs = qs.filter(subject__isnull=True)
        else:
            qs = qs.filter(subject_id=subject_id)

    if section_id:
        if section_id == "none":
            qs = qs.filter(section__isnull=True)
        else:
            qs = qs.filter(section_id=section_id)

    if topic_id:
        if topic_id == "none":
            qs = qs.filter(topic__isnull=True)
        else:
            qs = qs.filter(topic_id=topic_id)

    if subtopic_id:
        if subtopic_id == "none":
            qs = qs.filter(subtopic__isnull=True)
        else:
            qs = qs.filter(subtopic_id=subtopic_id)

    if olt_code:
        if olt_code == "none":
            qs = qs.filter(olt__isnull=True)
        else:
            # filter by the code string on the FK or the raw field
            qs = qs.filter(olt__code=olt_code) 
            
    if check_status:
        qs = qs.filter(check_status=check_status)

    # 3. Build context lists
    exams    = Question.objects.values_list("exam_name", flat=True).distinct().order_by("exam_name")
    years    = Question.objects.values_list("year", flat=True).distinct().order_by("year")
    subjects  = Subject.objects.order_by("name")
    olts      = OLT.objects.order_by("code")
    sections  = (
        Section.objects.filter(subject_id=subject_id)
        if subject_id and subject_id != "none"
        else Section.objects.none()
    )
    topics    = (
        Topic.objects.filter(section_id=section_id)
        if section_id and section_id != "none"
        else Topic.objects.none()
    )
    subtopics = (
        SubTopic.objects.filter(topic_id=topic_id)
        if topic_id and topic_id != "none"
        else SubTopic.objects.none()
    )

    total_count = qs.count()
    
   

    context = {
  
        "questions":      qs,
        "exams":          exams,
        "exam":           exam,
        "years":          years,
        "year":           year,
        "subjects":       subjects,
        "olts":           olts,
        "sections":       sections,
        "topics":         topics,
        "subtopics":      subtopics,
        "filter_year":    year,
        "filter_subject": subject_id,
        "filter_section": section_id,
        "filter_topic":   topic_id,
        "filter_subtopic":subtopic_id,
        "filter_olt":     olt_code,
        "filter_status": check_status,
        "total_count":    total_count,
        "category_choices": Question.CATEGORY_CHOICES,
    }
    
    return render(request,
                  'question/question_list.html',
                  context)

def ajax_question_sections(request, pk):
    q = get_object_or_404(Question, pk=pk)
    subj_id = request.GET.get('subject')
    sections = Section.objects.filter(subject_id=subj_id)
    return render(request,
                  'question/partials/section_filter_for_row.html',
                  {'q': q, 'sections': sections})

def ajax_question_topics(request, pk):
    q = get_object_or_404(Question, pk=pk)
    sec_id = request.GET.get('section')
    topics = Topic.objects.filter(section_id=sec_id)
    return render(request,
                  'question/partials/topic_filter_for_row.html',
                  {'q': q, 'topics': topics})

def ajax_question_subtopics(request, pk):
    q = get_object_or_404(Question, pk=pk)
    top_id = request.GET.get('topic')
    subtopics = SubTopic.objects.filter(topic_id=top_id)
    return render(request,
                  'question/partials/subtopic_filter_for_row.html',
                  {'q': q, 'subtopics': subtopics})


@require_POST
@staff_member_required
def check_save(request, pk):
    """
    Saves inline edits and marks question as 'checked'.
    Your front-end currently removes the row (empty response),
    which we keep intact.
    """
    q = get_object_or_404(Question, pk=pk)

    # Syllabus + OLT
    q.subject_id  = request.POST.get('subject')  or q.subject_id
    q.section_id  = request.POST.get('section')  or q.section_id
    q.topic_id    = request.POST.get('topic')    or q.topic_id
    q.subtopic_id = request.POST.get('subtopic') or q.subtopic_id
    q.olt_id      = request.POST.get('olt')      or q.olt_id
    q.category    = request.POST.get('category') or q.category

    # Question statement (HTML via Toast UI)
    q_html = request.POST.get('question_html')
    if q_html is not None:
        q.question_html = q_html
        

    # Options (plain strings)
    for f in ['option_a', 'option_b', 'option_c', 'option_d']:
        val = request.POST.get(f)
        if val is not None:
            setattr(q, f, val)

    # Correct option
    co = request.POST.get('correct_option')
    if co in ['a', 'b', 'c', 'd']:
        q.correct_option = co

    # Explanation (Markdown) if present
    exp_md = request.POST.get('explanation_html')
    
    if exp_md is not None:
        q.explanation_html= exp_md

    


    # Mark as checked (will enforce your validation in model.save)
    q.check_status = 'checked'
    q.save()

    # Keep the existing behavior: remove row on client (empty swap)
    return HttpResponse("")


@require_POST
@staff_member_required
def mark_review(request, pk):
    q = get_object_or_404(Question, pk=pk)
    q.check_status = 'review'
    q.save()
    return HttpResponse("")


@require_POST
@staff_member_required
def reset_status(request, pk):
    """
    Sets status back to pending and re-renders the row so it stays visible.
    """
    q = get_object_or_404(Question, pk=pk)
    q.check_status = 'pending'
    q.save()

    return render(
        request,
        "question/partials/question_row.html",
        {
            "q": q,
            "subjects": Subject.objects.order_by("name"),
            "olts": OLT.objects.order_by("code"),
        },
    )

@staff_member_required
def ajax_sections(request):
    subject_id = request.GET.get("subject")
    if subject_id and subject_id != "none":
        sections = Section.objects.filter(subject_id=subject_id).order_by("name")
    else:
        sections = Section.objects.none()
    return render(request, "question/partials/section_filter.html", {
        "sections": sections,
        "filter_section": request.GET.get("section"),
    })


@staff_member_required
def ajax_topics(request):
    section_id = request.GET.get("section")
    if section_id and section_id != "none":
        topics = Topic.objects.filter(section_id=section_id).order_by("name")
    else:
        topics = Topic.objects.none()
    return render(request, "question/partials/topic_filter.html", {
        "topics": topics,
        "filter_topic": request.GET.get("topic"),
    })


@staff_member_required
def ajax_subtopics(request):
    topic_id = request.GET.get("topic")
    if topic_id and topic_id != "none":
        subtopics = SubTopic.objects.filter(topic_id=topic_id).order_by("name")
    else:
        subtopics = SubTopic.objects.none()
    return render(request, "question/partials/subtopic_filter.html", {
        "subtopics": subtopics,
        "filter_subtopic": request.GET.get("subtopic"),
    })


@staff_member_required
def attempt_question(request):
    questions = Question.objects.all().order_by('id')  # You can order by subject/year etc too
    selected_question_id = request.GET.get('question')

    if selected_question_id:
        selected_question = get_object_or_404(Question, pk=selected_question_id)
    else:
        selected_question = questions.first()  # default to first question if none selected

    context = {
        'questions': questions,
        'selected_question': selected_question,
    }
    return render(request, 'question/attempt_question.html', context)
