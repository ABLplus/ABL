from django.shortcuts import render, redirect, get_object_or_404
from .models import Question, Subject
from .forms import QuestionForm
from django.contrib.admin.views.decorators import staff_member_required

# Add (Create) View
@staff_member_required
def add_question(request):
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('question_list')
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
            return redirect('question_list')
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
    questions = Question.objects.all().order_by('-created_at')

    # Get filter values from query params
    year = request.GET.get('year')
    subject_id = request.GET.get('subject')
    unlinked_only = request.GET.get('unlinked') == '1'

    # Apply filters
    if year:
        questions = questions.filter(year=year)
    if subject_id:
        questions = questions.filter(subject_id=subject_id)
    if unlinked_only:
        questions = questions.filter(subject__isnull=True)

    # Populate subject list for filter dropdown
    subjects = Subject.objects.all().order_by('name')

    context = {
        'questions': questions,
        'subjects': subjects,
        'filter_year': year,
        'filter_subject': subject_id,
        'filter_unlinked': unlinked_only,
        'total_count': questions.count(),
    }
    return render(request, 'question/question_list.html', context)

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