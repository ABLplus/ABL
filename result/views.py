# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from tests.models import *
from collections import Counter
from question.models import Subject

def test_result(request, test_id):

    test = get_object_or_404(Test, id=test_id, user=request.user)

    if test.status != 'completed':
        return redirect('dashboard')
    total = test.total_questions
    correct = test.correct_answers
    unattempted = test.unattempted
    wrong = test.wrong_answers()
    attempted = total - unattempted
    score = test.total_score

     # Get all test IDs for the user, ordered by ID
    test_ids = list(
        Test.objects.filter(user=request.user, status='completed')
        .order_by('id')
        .values_list('id', flat=True)
    )

    # Find the index of the current test
    try:
        current_index = test_ids.index(test.id)
    except ValueError:
        current_index = -1

    previous_test_id = test_ids[current_index - 1] if current_index > 0 else None
    next_test_id = test_ids[current_index + 1] if current_index < len(test_ids) - 1 else None

    # Your core metric
    percent_wrong = round((wrong / attempted) * 100, 2) if attempted > 0 else 0

    # Scoring system
    MARKS_CORRECT = 2
    MARKS_WRONG = -2 / 3

    def compute_score(correct_count, wrong_count):
        return round((correct_count * MARKS_CORRECT) + (wrong_count * MARKS_WRONG), 2)

    attempt_types = []

    # Main 3 attempt types
    for label, key, total_attempts, wrong_attempts in [
        ('Sureshot', 'sureshot', test.sureshot_attempts, test.sureshot_wrong),
        ('Applied', 'applied', test.applied_attempts, test.applied_wrong),
        ('Guesswork', 'guesswork', test.guesswork_attempts, test.guesswork_wrong),
    ]:
        correct_attempts = total_attempts - wrong_attempts
        percent_type_wrong = round((wrong_attempts / total_attempts) * 100, 2) if total_attempts > 0 else 0
        marks = compute_score(correct_attempts, wrong_attempts)

        attempt_types.append({
            'label': label,
            'key': key,
            'total': total_attempts,
            'wrong': wrong_attempts,
            'correct': correct_attempts,
            'percent_wrong': percent_type_wrong,
            'marks': marks,
            'url': f'/result/{test.id}/{key}/',
        })

    # Optional: Blind Attempt (only shown if used)
    if test.blind_wrong > 0:
        blind_attempts = unattempted
        blind_correct = blind_attempts - test.blind_wrong
        blind_marks = compute_score(blind_correct, test.blind_wrong)

        attempt_types.append({
            'label': 'Blind Attempt',
            'key': 'blind',
            'total': blind_attempts,
            'wrong': test.blind_wrong,
            'correct': blind_correct,
            'percent_wrong': round((test.blind_wrong / blind_attempts) * 100, 2) if blind_attempts > 0 else 0,
            'marks': blind_marks,
            'url': f'/result/{test.id}/blind/',
        })

    context = {
        'test': test,
        'total': total,
        'correct': correct,
        'wrong': wrong,
        'attempted': attempted,
        'unattempted': unattempted,
        'score': score,
        'percent_wrong': percent_wrong,
        'attempt_types': attempt_types,
        'previous_test_id': previous_test_id,
        'next_test_id': next_test_id,
    }

    return render(request, 'result/test_result.html', context)


from django.shortcuts import render, get_object_or_404
from collections import Counter
from tests.models import QuestionLog, Test
from question.models import Subject

def attempt_type_detail(request, test_id, attempt_type):
    test = get_object_or_404(Test, id=test_id, user=request.user)  # 1 DB hit

    # Pull all logs and their linked question & subject in one query
    base_logs = QuestionLog.objects.filter(test=test).select_related('question__subject')  # 1 DB hit
    logs = base_logs

    # Apply attempt_type filter
    if attempt_type in ['sureshot', 'applied', 'guesswork', 'blind']:
        logs = logs.filter(attempt_type=attempt_type)

        result_type = request.GET.get('result')
        if result_type in ['right', 'wrong']:
            logs = logs.filter(attempt_result=result_type).exclude(attempt_type__in=['unattempted', 'blind'])
        else:
            result_type = ''
    elif attempt_type == 'right':
        logs = logs.filter(attempt_result='right').exclude(attempt_type__in=['unattempted', 'blind'])
        result_type = 'right'
    elif attempt_type == 'wrong':
        logs = logs.filter(attempt_result='wrong').exclude(attempt_type__in=['unattempted', 'blind'])
        result_type = 'wrong'
    elif attempt_type == 'unattempted':
        logs = logs.filter(attempt_type__in=['unattempted', 'blind'])
        result_type = 'unattempted'
    else:
        logs = QuestionLog.objects.none()
        result_type = ''

    # Evaluate logs only ONCE
    logs = list(logs.order_by('serial'))  # 1 DB hit (all filtering + sorting)

    # Subject count using already-fetched objects (no DB hit)
    subject_counter = Counter([log.question.subject.name for log in logs if log.question.subject])
    subjects = [{'name': name, 'count': count} for name, count in sorted(subject_counter.items())]

    subject_filter = request.GET.get('subject')
    if not subject_filter and len(subjects) == 1:
        subject_filter = subjects[0]['name']

    if subject_filter:
        logs = [log for log in logs if log.question.subject and log.question.subject.name == subject_filter]

    context = {
        'test': test,
        'logs': logs,
        'log_count': len(logs),
        'attempt_type': attempt_type.capitalize(),
        'subjects': subjects,
        'selected_subject': subject_filter,
        'selected_result': result_type,
    }

    return render(request, 'result/attempt_type_detail.html', context)





