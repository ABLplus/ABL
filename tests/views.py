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
from django.views.decorators.http import require_POST
from services.n2 import finalise_session


MARKS_RIGHT = Decimal('2.0')
MARKS_WRONG = Decimal('2.0') / Decimal('3.0')


def submit_test(request, test_id):
    """
    Finalise a Test attempt and redirect to result page.
    """
    test = get_object_or_404(
        Test,
        id=test_id,
        user=request.user,
    )

    # Guard: already submitted
    if test.status == "completed":
        return redirect("test_result", test_id=test.id)

    # Only pending tests can be submitted
    if test.status == "pending":
        finalise_session(test, mode="test")

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
        test_type = "full_length"
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
