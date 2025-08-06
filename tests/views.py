from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from question.models import Question
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from decimal import Decimal
from django.contrib import messages
from syllabus.models import *
from django.http import HttpResponse
from django.urls import reverse
from django.http import HttpResponse, HttpResponseBadRequest



MARKS_RIGHT = Decimal('2.0')
MARKS_WRONG = Decimal('2.0') / Decimal('3.0')


def submit_test(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)
    if test.status == "completed":
        return redirect("test_result", test_id=test.id)

    # ─── 1. Fetch logs (Question + Topic pre-fetched) ───────────────────
    logs = (test.questionlog_set
            .select_related("question__topic", "topic")
            .all())
    total_questions = len(logs)

    # ─── 2. Existing summaries cache ────────────────────────────────────
    contrib_logs = [l for l in logs                      # sureshot/applied/guesswork
                    if l.attempt_type in ("sureshot", "applied", "guesswork")]

    question_ids = {l.question_id for l in contrib_logs}
    topic_ids    = {(l.topic_id or l.question.topic_id) for l in contrib_logs}

    q_map = {s.question_id: s for s in
             QuestionAttemptSummary.objects.filter(user=request.user,
                                                   question_id__in=question_ids)}
    t_map = {s.topic_id: s for s in
             TopicAttemptSummary.objects.filter(user=request.user,
                                                topic_id__in=topic_ids,
                                                mode="test")}

    q_new, q_upd, t_new, t_upd = [], [], [], []

    # ─── 3. Test-level counters ─────────────────────────────────────────
    correct_answers = wrong_answers = unattempted = 0
    sureshot_cnt = applied_cnt = guess_cnt = 0
    sureshot_wrong = applied_wrong = guess_wrong = 0
    blind_cnt = blind_wrong = 0

    # ─── 4. Iterate once over logs ──────────────────────────────────────
    for log in logs:
        aid = log.attempt_type
        result = log.attempt_result

        if aid in ("sureshot", "applied", "guesswork"):
            # Marks & summaries
            if result == "right":
                correct_answers += 1
            else:
                wrong_answers += 1

            if aid == "sureshot":
                sureshot_cnt += 1
                if result == "wrong":
                    sureshot_wrong += 1
            elif aid == "applied":
                applied_cnt += 1
                if result == "wrong":
                    applied_wrong += 1
            elif aid == "guesswork":
                guess_cnt += 1
                if result == "wrong":
                    guess_wrong += 1

            # QUESTION summary
            qs = q_map.get(log.question_id)
            if not qs:
                qs = QuestionAttemptSummary(
                    user=request.user,
                    question=log.question,
                    topic=log.question.topic
                )
                q_new.append(qs)
                q_map[log.question_id] = qs

            qs.total_attempts += 1
            if result == "right":
                qs.correct_attempts += 1
            else:
                qs.wrong_attempts += 1

            if aid == "sureshot":
                qs.sureshot_attempts += 1
                if result == "wrong":
                    qs.sureshot_wrong += 1
            elif aid == "applied":
                qs.applied_attempts += 1
                if result == "wrong":
                    qs.applied_wrong += 1
            elif aid == "guesswork":
                qs.guesswork_attempts += 1
                if result == "wrong":
                    qs.guesswork_wrong += 1

            qs.net_marks = (qs.correct_attempts * MARKS_RIGHT
                            - qs.wrong_attempts   * MARKS_WRONG)

            if qs not in q_new:
                q_upd.append(qs)

            # TOPIC summary  (mode='test')
            topic_id = log.topic_id or log.question.topic_id
            if topic_id is not None:
                ts = t_map.get(topic_id)
                if not ts:
                    ts = TopicAttemptSummary(
                        user=request.user,
                        topic_id=topic_id,
                        mode="test"
                    )
                    t_new.append(ts)
                    t_map[topic_id] = ts

                ts.total_attempts += 1
                if result == "right":
                    ts.correct_attempts += 1
                else:
                    ts.wrong_attempts += 1

                if aid == "sureshot":
                    ts.sureshot_attempts += 1
                    if result == "wrong":
                        ts.sureshot_wrong += 1
                elif aid == "applied":
                    ts.applied_attempts += 1
                    if result == "wrong":
                        ts.applied_wrong += 1
                elif aid == "guesswork":
                    ts.guesswork_attempts += 1
                    if result == "wrong":
                        ts.guesswork_wrong += 1

                ts.net_marks = (ts.correct_attempts * MARKS_RIGHT
                                - ts.wrong_attempts   * MARKS_WRONG)

                if ts not in t_new:
                    t_upd.append(ts)

        else:          # 'blind' or 'unattempted'
            unattempted += 1
            if aid == "blind":
                blind_cnt += 1
                if result == "wrong":
                    blind_wrong += 1

    total_score = (correct_answers * MARKS_RIGHT
                   - wrong_answers  * MARKS_WRONG)

    # ─── 5. Transactional write ────────────────────────────────────────
    with transaction.atomic():
        if q_new:
            QuestionAttemptSummary.objects.bulk_create(q_new, ignore_conflicts=True)
        if q_upd:
            QuestionAttemptSummary.objects.bulk_update(
                q_upd,
                ['total_attempts', 'correct_attempts', 'wrong_attempts',
                 'sureshot_attempts', 'applied_attempts', 'guesswork_attempts',
                 'sureshot_wrong', 'applied_wrong', 'guesswork_wrong',
                 'net_marks']
            )

        if t_new:
            TopicAttemptSummary.objects.bulk_create(t_new, ignore_conflicts=True)
        if t_upd:
            TopicAttemptSummary.objects.bulk_update(
                t_upd,
                ['total_attempts', 'correct_attempts', 'wrong_attempts',
                 'sureshot_attempts', 'applied_attempts', 'guesswork_attempts',
                 'sureshot_wrong', 'applied_wrong', 'guesswork_wrong',
                 'net_marks']
            )

        # Update Test row (blind stats kept here only)
        test.total_questions   = total_questions
        test.correct_answers   = correct_answers
        test.unattempted       = unattempted
        test.total_score       = total_score

        test.sureshot_attempts = sureshot_cnt
        test.applied_attempts  = applied_cnt
        test.guesswork_attempts= guess_cnt
        test.blind_attempts    = blind_cnt

        test.sureshot_wrong    = sureshot_wrong
        test.applied_wrong     = applied_wrong
        test.guesswork_wrong   = guess_wrong
        test.blind_wrong       = blind_wrong

        test.status            = "completed"
        test.end_time          = timezone.now()
        test.save()

        attempt_count = len(contrib_logs)
        request.user.profile.register_attempt(increment=attempt_count)

    return redirect("test_result", test_id=test.id)

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

@login_required
def start_test(request):
    
    if request.method != "POST":
        return redirect("dashboard")

    user  = request.user
    ttype = request.POST.get("type")

    # ── 0. global guard ───────────────────────────────────────────────
    if Test.objects.filter(user=user, status="pending").count() >= 2:
        messages.warning(request, "You already have a pending test. "
                                  "Finish it before starting a new one.")
        print(1)
        return _hx_redirect_or_normal(request, reverse("dashboard"))

    # ── 1. branch-specific template & question set ────────────────────
    if ttype == "exam_year":
        exam_id = int(request.POST["exam"])
        year    = int(request.POST["year"])
        exam    = get_object_or_404(Exam, pk=exam_id)

        template, _ = TestTemplate.objects.get_or_create(
            user=user,
            exam_id=exam_id,
            year=year,
            subject=None,
            section=None,
        )

        questions = Question.objects.filter(exam_name=exam.name, year=year).order_by("id")
        if not questions:
            messages.error(request, "No questions found for that exam & year.")
            print(2)
            print(exam.name)
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        test_name = f"{exam.name} {year}"
        test_type = "full_length"

    elif ttype == "subject":
        subject_id = int(request.POST["subject"])
        subject    = get_object_or_404(Subject, pk=subject_id)

        template, _ = TestTemplate.objects.get_or_create(
            user=user,
            subject_id=subject_id,
            exam=None,
            year=None,
            section=None,
        )

        qs_all = Question.objects.filter(subject_id=subject_id)
        questions = qs_all.order_by("?")[:100] if qs_all.count() > 100 else qs_all.order_by("id")
        if not questions:
            messages.error(request, "No questions found for that subject.")
            print(3)
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        test_name = f"{subject.name} – Subject Test"
        test_type = "sectional"
        year      = None  # not used for subject tests
        exam      = None

    else:
        messages.error(request, "Invalid test type.")
        print(4)
        return _hx_redirect_or_normal(request, reverse("dashboard"))

    # ── 2. resume if template already has pending test ────────────────
    pending = Test.objects.filter(user=user, template=template, status="pending").first()
    if pending:
        msg = (f"You already have a pending test for {exam.name} {year}."
               if ttype == "exam_year"
               else f"You already have a pending test for {subject.name}.")
        messages.warning(request, msg)
        print(5)
        return _hx_redirect_or_normal(request, reverse("dashboard"))
        

    # ── 3. create Test & logs atomically ──────────────────────────────
    with transaction.atomic():
        serial = template.no_of_attempts + 1

        test = Test.objects.create(
            user=user,
            template=template,
            attempt_serial=serial,
            name=test_name,
            test_type=test_type,
            exam=str(exam) if exam else None,
            year=year,
            total_questions=questions.count(),
            start_time=timezone.now(),
            status="pending",
        )

        QuestionLog.objects.bulk_create(
            [
                QuestionLog(user=user, question=q, test=test, serial=i)
                for i, q in enumerate(questions, start=1)
            ],
            batch_size=500,
        )

        template.no_of_attempts = serial
        template.save(update_fields=["no_of_attempts"])

    # ── 4. send user to first question ────────────────────────────────
    redirect_url = reverse("take_test", args=[test.id, 1])
    print(6)           # ✅
    return _hx_redirect_or_normal(request, redirect_url)


# helper: HTMX-aware redirect
def _hx_redirect_or_normal(request, url: str):
    if request.headers.get("HX-Request") == "true":
        resp = HttpResponse(status=204)
        resp["HX-Redirect"] = url
        return resp
    return redirect(url)

# @login_required
# def reset_question(request, test_id, serial):
#     if request.method == 'POST':
#         qlog = get_object_or_404(QuestionLog, test_id=test_id, user=request.user, serial=serial)
#         qlog.user_answered = None
#         qlog.attempt_type = 'unattempted'
#         qlog.attempt_result = None
#         qlog.save()
#     return redirect('take_test', test_id=test_id, serial=serial)

# @login_required
# def take_test(request, test_id, serial):
#     test = get_object_or_404(Test, id=test_id, user=request.user)
#     question_log = get_object_or_404(QuestionLog, test=test, serial=serial)

#     if request.method == 'POST':
#         user_answered = request.POST.get('option')
#         attempt_type = request.POST.get('attempt_type')

#         # Save user answer
#         question_log.user_answered = user_answered
#         question_log.attempt_type = attempt_type
#         question_log.timestamp=timezone.now()

#         # Calculate result

#         if user_answered.lower() == question_log.question.correct_option.lower():
#             question_log.attempt_result = 'right'
#         else:
#             question_log.attempt_result = 'wrong'

#         question_log.save()

#         # Move to next question
#         next_serial = serial + 1
#         if next_serial > test.total_questions:
#             return redirect('proceed_to_submit', test_id=test.id)
#         else:
#             return redirect('take_test', test_id=test.id, serial=next_serial)

#     prev_serial = serial - 1 if serial > 1 else None
#     next_serial = serial + 1 if serial < test.total_questions else None

#     all_question_logs = test.questionlog_set.only('id', 'serial', 'attempt_type').order_by('serial')
#     context = {
#         'test': test,
#         'question_log': question_log,
#         'current_serial': serial,
#         'total_questions': test.total_questions,
#         'prev_serial': prev_serial,
#         'next_serial': next_serial,
#         'all_question_logs':all_question_logs,
#     }
#     return render(request, 'tests/take_test.html', context)

def _is_htmx(request):
    # Works whether or not django-htmx middleware is installed
    return request.headers.get("HX-Request") == "true" or getattr(request, "htmx", False)

def _build_context(test, serial):
    question_log = get_object_or_404(QuestionLog, test=test, serial=serial)
    q = question_log.question

    prev_serial = serial - 1 if serial > 1 else None
    next_serial = serial + 1 if serial < test.total_questions else None
    all_question_logs = (
        test.questionlog_set.only("id", "serial", "attempt_type")
        .order_by("serial")
    )

    return {
        "test": test,
        "question_log": question_log,
        "current_serial": serial,
        "total_questions": test.total_questions,
        "prev_serial": prev_serial,
        "next_serial": next_serial,
        "all_question_logs": all_question_logs,
        # NEW:
        "options": [
            {"key": "a", "text": q.option_a},
            {"key": "b", "text": q.option_b},
            {"key": "c", "text": q.option_c},
            {"key": "d", "text": q.option_d},
        ],
    }


def _render_question_area(request, context):
    """
    Render the partial when HTMX; otherwise the full page that includes it.
    """
    if _is_htmx(request):
        return render(request, "tests/partials/_question_area.html", context)
    return render(request, "tests/take_test.html", context)


# ---- views ----------------------------------------------------------------

@login_required
def take_test(request, test_id, serial):
    """
    GET:
      - Normal request -> full page (includes _question_area.html)
      - HTMX request   -> only the question area partial
    Optional ?serial=N in the querystring overrides the path serial (used by 'Go' box).
    """
    test = get_object_or_404(Test, id=test_id, user=request.user)

    # Allow the goto form to pass ?serial=N
    try:
        serial = int(request.GET.get("serial", serial))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid serial")

    # Clamp to valid range
    if serial < 1 or serial > test.total_questions:
        return HttpResponseBadRequest("Serial out of range")

    context = _build_context(test, serial)
    return _render_question_area(request, context)


@login_required
def save_answer(request, test_id, serial):
    """
    POST:
      Saves the answer & attempt_type, sets attempt_result, then:
        - If more questions remain: return the next question (partial for HTMX, redirect otherwise)
        - Else: redirect to 'proceed_to_submit'
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    test = get_object_or_404(Test, id=test_id, user=request.user)
    qlog = get_object_or_404(QuestionLog, test=test, serial=serial)

    user_answered = (request.POST.get("option") or "").strip().lower()
    attempt_type = (request.POST.get("attempt_type") or "").strip().lower()

    if user_answered not in {"a", "b", "c", "d"}:
        return HttpResponseBadRequest("Invalid option")

    if attempt_type not in {"sureshot", "applied", "guesswork"}:
        return HttpResponseBadRequest("Invalid attempt_type")

    # Save user answer
    qlog.user_answered = user_answered
    qlog.attempt_type = attempt_type
    qlog.timestamp = timezone.now()
    qlog.attempt_result = (
        "right" if user_answered == (qlog.question.correct_option or "").lower() else "wrong"
    )
    qlog.save()

    # Advance to next question or submit
    next_serial = serial + 1
    if next_serial > test.total_questions:
        submit_url = reverse("proceed_to_submit", args=[test.id])

        if _is_htmx(request):
            # In HTMX, redirect via HX-Redirect header
            response = HttpResponse(status=204)
            response["HX-Redirect"] = submit_url
            return response
        return redirect(submit_url)

    # Show next question
    context = _build_context(test, next_serial)
    if _is_htmx(request):
        return render(request, "tests/partials/_question_area.html", context)
    return redirect("take_test", test_id=test.id, serial=next_serial)


@login_required
def reset_question(request, test_id, serial):
    """
    POST:
      Clears the user's answer/attempt on the given question and re-renders it.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    test = get_object_or_404(Test, id=test_id, user=request.user)
    qlog = get_object_or_404(QuestionLog, test=test, serial=serial)

    # Clear user state
    qlog.user_answered = None
    qlog.attempt_type = None
    qlog.attempt_result = None
    qlog.timestamp = timezone.now()
    qlog.save()

    context = _build_context(test, serial)
    if _is_htmx(request):
        return render(request, "tests/partials/_question_area.html", context)
    return redirect("take_test", test_id=test.id, serial=serial)