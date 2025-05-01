from django.shortcuts import render, redirect, get_object_or_404
from .models import Question
from .forms import QuestionForm

# Add (Create) View
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
def delete_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if request.method == 'POST':
        question.delete()
        return redirect('question_list')
    return render(request, 'question/delete_question.html', {'question': question})

# List View (to view all questions)
def question_list(request):
    questions = Question.objects.all().order_by('-created_at')
    return render(request, 'question/question_list.html', {'questions': questions})


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