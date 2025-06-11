from django.shortcuts import render, redirect, get_object_or_404
from .models import Test, QuestionLog, QuestionAttemptSummary
from question.models import Question
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from decimal import Decimal



MARKS_RIGHT = Decimal('2.0')
MARKS_WRONG = Decimal('-2.0') / Decimal('3.0')




def submit_test(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)

    # ✅ Skip processing if already completed
    if test.status == 'completed':
        return redirect('test_result', test_id=test.id)

    logs = test.questionlog_set.select_related('question')

    # Split into logs that contribute to performance and all logs for test summary
    performance_logs = logs.filter(attempt_type__in=['sureshot', 'applied', 'guesswork'])

    # STEP 1: Update/Create QuestionAttemptSummary in bulk
    question_ids = performance_logs.values_list('question_id', flat=True)
    existing_summaries = QuestionAttemptSummary.objects.filter(user=request.user, question_id__in=question_ids)
    summary_map = {s.question_id: s for s in existing_summaries}

    to_create, to_update = [], []

    correct_count = 0
    wrong_count = 0

    for log in performance_logs:
        # 🚫 Skip blind attempts entirely for summary
        if log.attempt_type == 'blind':
            continue

        qid = log.question.id
        summary = summary_map.get(qid)

        if not summary:
            summary = QuestionAttemptSummary(user=request.user, question=log.question)
            summary_map[qid] = summary
            to_create.append(summary)

        summary.total_attempts += 1

        if log.attempt_result == 'right':
            summary.correct_attempts += 1
            correct_count += 1
        else:
            summary.wrong_attempts += 1
            wrong_count += 1

        # Attempt type-specific fields
        if log.attempt_type == 'sureshot':
            summary.sureshot_attempts += 1
            if log.attempt_result == 'wrong':
                summary.sureshot_wrong += 1
        elif log.attempt_type == 'applied':
            summary.applied_attempts += 1
            if log.attempt_result == 'wrong':
                summary.applied_wrong += 1
        elif log.attempt_type == 'guesswork':
            summary.guesswork_attempts += 1
            if log.attempt_result == 'wrong':
                summary.guesswork_wrong += 1

        # Net marks calculation (blind already excluded)
        summary.net_marks = (Decimal(summary.correct_attempts) * MARKS_RIGHT) - (Decimal(summary.wrong_attempts) * MARKS_WRONG)

        if summary not in to_create:
            to_update.append(summary)




    # STEP 2: Aggregate logs to update Test entity
    total_questions = logs.count()
    correct_answers = logs.filter(attempt_result='right').exclude(attempt_type='blind').count()
    unattempted = logs.filter(attempt_type__in=['unattempted', 'blind']).count()
    wrong_answers = total_questions-unattempted-correct_answers

    sureshot = logs.filter(attempt_type='sureshot')
    applied = logs.filter(attempt_type='applied')
    guesswork = logs.filter(attempt_type='guesswork')
    blind = logs.filter(attempt_type='blind')


    total_score=  correct_answers*2 -(wrong_answers*2/3)


    # STEP 3: Save everything atomically
    with transaction.atomic():
        if to_create:
            QuestionAttemptSummary.objects.bulk_create(to_create)
        if to_update:
            QuestionAttemptSummary.objects.bulk_update(
                to_update,
                [
                    'total_attempts', 'correct_attempts', 'wrong_attempts',
                    'sureshot_attempts', 'applied_attempts', 'guesswork_attempts', 'blind_attempts',
                    'sureshot_wrong', 'applied_wrong', 'guesswork_wrong','blind_wrong',
                    'net_marks'
                ]
            )

        test.total_questions = total_questions
        test.correct_answers = correct_answers
        test.unattempted = unattempted
        test.total_score = total_score

        test.sureshot_attempts = sureshot.count()
        test.applied_attempts = applied.count()
        test.guesswork_attempts = guesswork.count()


        test.sureshot_wrong = sureshot.filter(attempt_result='wrong').count()
        test.applied_wrong = applied.filter(attempt_result='wrong').count()
        test.guesswork_wrong = guesswork.filter(attempt_result='wrong').count()
        test.blind_wrong= blind.filter(attempt_result='wrong').count()

        test.status = 'completed'
        test.end_time = timezone.now()
        test.save()

    return redirect('test_result', test_id=test.id)


def blind_attempt(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)

    # Find the next unattempted question
    next_unattempted = test.questionlog_set.filter(
        Q(attempt_type__isnull=True) | Q(attempt_type='unattempted')
    ).order_by('serial').first()


    if not next_unattempted:
        test.blind_attempts = test.questionlog_set.filter(attempt_type='blind').count()
        test.save(update_fields=['blind_attempts'])
        return redirect('submit_test', test_id=test.id)


    if request.method == 'POST':
        selected_option = request.POST.get('selected_option')
        if selected_option:
            with transaction.atomic():
                # Save blind attempt
                next_unattempted.user_answered = selected_option
                next_unattempted.attempt_type = 'blind'
                if selected_option.lower() == next_unattempted.question.correct_option.lower():
                    next_unattempted.attempt_result = 'right'
                else:
                    next_unattempted.attempt_result = 'wrong'
                next_unattempted.save()

            # After saving, refresh view for next unattempted question
            return redirect('blind_attempt', test_id=test.id)

    context = {
        'test': test,
        'question_log': next_unattempted,
    }
    return render(request, 'tests/blind_attempt.html', context)


def proceed_to_submit(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)

    attempt_logs = test.questionlog_set.all()

    total_questions = test.total_questions
    attempted_questions = attempt_logs.filter(attempt_type__in=['sureshot', 'applied', 'guesswork']).count()

    sureshot = attempt_logs.filter(attempt_type='sureshot').count()
    applied = attempt_logs.filter(attempt_type='applied').count()
    guesswork = attempt_logs.filter(attempt_type='guesswork').count()

    unattempted = total_questions - attempted_questions

    highest_attempt = attempt_logs.exclude(user_answered__isnull=True).aggregate(Max('serial'))['serial__max']
    if highest_attempt:
            if highest_attempt == test.total_questions:
                back_serial = highest_attempt
            else:
                back_serial = highest_attempt + 1

    else:
            back_serial = 1  # No attempt yet


    context = {
        'test': test,
        'total_questions': total_questions,
        'attempted_questions': attempted_questions,
        'sureshot': sureshot,
        'applied': applied,
        'guesswork': guesswork,
        'unattempted': unattempted,
        'back_serial': back_serial,
    }

    return render(request, 'tests/proceed_to_submit.html', context)

# @login_required
# def dashboard(request):
#     years = list(range(2000, 2025))  # 2000 to 2024 inclusive
#     return render(request, 'user/dashboard.html', {'years': years})


@login_required
def start_test(request):
    if request.method == 'POST':
        year = int(request.POST.get('year'))

        # Check for a pending test for the same year
        pending_test = Test.objects.filter(
            user=request.user,
            year=year,
            status='pending',
        ).first()

        if pending_test:
            return redirect('take_test', test_id=pending_test.id, serial=1)

        # Fetch questions for selected year
        questions = Question.objects.filter(year=year).order_by('id')

        if not questions.exists():
            return redirect('dashboard')

        # Get the last attempt_serial for completed tests
        last_serial = (
            Test.objects.filter(user=request.user, year=year, status='completed')
            .order_by('-attempt_serial')
            .values_list('attempt_serial', flat=True)
            .first()
        ) or 0  # default to 0 if none exist

        new_serial = last_serial + 1

        with transaction.atomic():
            # Create the test with attempt_serial
            test = Test.objects.create(
                user=request.user,
                name=f"UPSC Prelims GS-I {year}",
                year=year,
                total_questions=questions.count(),
                test_type='full_length',
                attempt_serial=new_serial,
                start_time=timezone.now()
            )

            # Create QuestionLogs
            question_logs = [
                QuestionLog(
                    user=request.user,
                    question=q,
                    test=test,
                    serial=idx,
                )
                for idx, q in enumerate(questions, start=1)
            ]

            QuestionLog.objects.bulk_create(question_logs)

        return redirect('take_test', test_id=test.id, serial=1)

    return redirect('dashboard')



@login_required
def reset_question(request, test_id, serial):
    if request.method == 'POST':
        qlog = get_object_or_404(QuestionLog, test_id=test_id, user=request.user, serial=serial)
        qlog.user_answered = None
        qlog.attempt_type = 'unattempted'
        qlog.attempt_result = None
        qlog.save()
    return redirect('take_test', test_id=test_id, serial=serial)




@login_required
def take_test(request, test_id, serial):
    test = get_object_or_404(Test, id=test_id, user=request.user)
    question_log = get_object_or_404(QuestionLog, test=test, serial=serial)

    if request.method == 'POST':
        user_answered = request.POST.get('option')
        attempt_type = request.POST.get('attempt_type')

        # Save user answer
        question_log.user_answered = user_answered
        question_log.attempt_type = attempt_type
        question_log.timestamp=timezone.now()

        # Calculate result

        if user_answered.lower() == question_log.question.correct_option.lower():
            question_log.attempt_result = 'right'
        else:
            question_log.attempt_result = 'wrong'

        question_log.save()

        # Move to next question
        next_serial = serial + 1
        if next_serial > test.total_questions:
            return redirect('proceed_to_submit', test_id=test.id)
        else:
            return redirect('take_test', test_id=test.id, serial=next_serial)

    prev_serial = serial - 1 if serial > 1 else None
    next_serial = serial + 1 if serial < test.total_questions else None

    all_question_logs = test.questionlog_set.only('id', 'serial', 'attempt_type').order_by('serial')
    context = {
        'test': test,
        'question_log': question_log,
        'current_serial': serial,
        'total_questions': test.total_questions,
        'prev_serial': prev_serial,
        'next_serial': next_serial,
        'all_question_logs':all_question_logs,
    }
    return render(request, 'tests/take_test.html', context)