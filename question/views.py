
from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from syllabus.models import *
from .forms import QuestionForm, QuestionRowForm
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Count, Q

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
            qs = qs.filter(olt__code=olt_code) | qs.filter(olt_type=olt_code)

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
def check_save(request, pk):
    q = get_object_or_404(Question, pk=pk)
    q.subject_id  = request.POST.get('subject')  or q.subject_id
    q.section_id  = request.POST.get('section')  or q.section_id
    q.topic_id    = request.POST.get('topic')    or q.topic_id
    q.subtopic_id = request.POST.get('subtopic') or q.subtopic_id
    q.olt_id = request.POST.get('olt') or q.olt_id
    q.check_status = 'checked'
    q.save()
    return HttpResponse("")  # empty body; HTMX will delete the row

@require_POST
def mark_review(request, pk):
    q = get_object_or_404(Question, pk=pk)
    q.check_status = 'review'
    q.save()
    return HttpResponse("") 

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
