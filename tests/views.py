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

from datetime import timedelta
import random
from django.db.models import Subquery
from tests.models import Test, TestTemplate, QuestionLog, QuestionAttemptSummary



MARKS_RIGHT = Decimal('2.0')
MARKS_WRONG = Decimal('2.0') / Decimal('3.0')




# models used:
# from tests.models import Test, TestTemplate, QuestionLog, QuestionAttemptSummary
# from question.models import Question, Subject, Section, Exam

# --- helper: smart selection for large pools ---------------------------------


def select_questions_topic_smart(
    *,
    user,
    base_qs,                         # pre-filtered Question queryset for this test scope
    subject=None,
    section=None,
    total_n: int = 100,
    wrong_ratio: float = 0.10,
    cooldown_days: int = 2,
    recent_limit: int = 200,         # "latest 200 attempted" exclusion
    mix_oldest_window: int = 500,    # "oldest 500 attempted" window for mix-fill
    seed=None,
):
    """
    Topic-scoped selector.

    1) fresh for fresh_required
    2) wrong attempted (exclude cooldown OR latest 200 attempted)
    3) fresh again if available; else attempted mix (non-recent) random from oldest 500 attempted
    4) last resort: use from excluded recent pool
    """

    assert (subject is None) ^ (section is None), "Provide exactly one: subject or section"
    rnd = random.Random(seed) if seed is not None else random

    wrong_required = int(round(total_n * wrong_ratio))
    fresh_required = max(total_n - wrong_required, 0)

    print(base_qs.count())

    # 1) topic_ids  (your exact block)
    if subject is not None:
        section_ids = Section.objects.filter(subject=subject).values("id")
        topic_ids = Topic.objects.filter(section_id__in=Subquery(section_ids)).values("id")
    else:
        topic_ids = Topic.objects.filter(section=section).values("id")

    base_ids = base_qs.values("id")

    qas = QuestionAttemptSummary.objects.filter(
        user=user,
        topic_id__in=Subquery(topic_ids),
        question_id__in=Subquery(base_ids),
    )

    selected = []
    selected_set = set()

    # ----------------------------
    # Build "recent excluded" set in this scope:
    # recent = (cooldown window) OR (latest N attempts)
    # ----------------------------
    cutoff = timezone.now() - timedelta(days=cooldown_days)

    recent_by_days_ids = list(
        qas.filter(last_attempted__gte=cutoff)
           .values_list("question_id", flat=True)
    )

    recent_by_count_ids = list(
        qas.order_by("-last_attempted")
           .values_list("question_id", flat=True)[:recent_limit]
    )

    recent_excluded_set = set(recent_by_days_ids) | set(recent_by_count_ids)

    # Non-recent attempted pool (eligible attempted)
    old_qas = qas.exclude(question_id__in=recent_excluded_set)

    # ----------------------------
    # 1) Fresh for fresh_required
    # ----------------------------
    attempted_ids_subq = qas.values("question_id")
    fresh_qs = base_qs.exclude(id__in=Subquery(attempted_ids_subq))

    fresh_ids = list(fresh_qs.values_list("id", flat=True))
    rnd.shuffle(fresh_ids)

    take1 = fresh_ids[:min(fresh_required, total_n)]
    selected.extend(take1)
    selected_set.update(take1)

    # ----------------------------
    # 2) Wrong attempted (exclude recent)
    # ----------------------------
    need = total_n - len(selected)
    if need > 0 and wrong_required > 0:
        take_wrong = min(wrong_required, need)

        wrong_old_ids = list(
            old_qas.filter(wrong_attempts__gt=0)
                   .exclude(question_id__in=selected_set)
                   .order_by("-wrong_attempts", "-total_attempts", "last_attempted")
                   .values_list("question_id", flat=True)[:take_wrong]
        )
        selected.extend(wrong_old_ids)
        selected_set.update(wrong_old_ids)

    # ----------------------------
    # 3) Fill remaining:
    #    3a) fresh again if available
    # ----------------------------
    need = total_n - len(selected)
    if need > 0:
        remaining_fresh = [qid for qid in fresh_ids if qid not in selected_set]
        take_more_fresh = remaining_fresh[:need]
        selected.extend(take_more_fresh)
        selected_set.update(take_more_fresh)

    #    3b) else attempted mix (non-recent) random from oldest attempted window
    need = total_n - len(selected)
    if need > 0:
        oldest_window_ids = list(
            old_qas.exclude(question_id__in=selected_set)
                   .order_by("last_attempted")
                   .values_list("question_id", flat=True)[:mix_oldest_window]
        )
        rnd.shuffle(oldest_window_ids)
        mix_ids = oldest_window_ids[:need]
        selected.extend(mix_ids)
        selected_set.update(mix_ids)

    # ----------------------------
    # 4) LAST RESORT: use from excluded recent pool
    #    (prefer recent wrongs first, then any recent)
    # ----------------------------
    need = total_n - len(selected)
    if need > 0:
        recent_qas = qas.filter(question_id__in=recent_excluded_set).exclude(question_id__in=selected_set)

        recent_wrong_ids = list(
            recent_qas.filter(wrong_attempts__gt=0)
                      .order_by("-wrong_attempts", "-total_attempts", "last_attempted")
                      .values_list("question_id", flat=True)[:need]
        )
        selected.extend(recent_wrong_ids)
        selected_set.update(recent_wrong_ids)

        need = total_n - len(selected)
        if need > 0:
            recent_any_ids = list(
                recent_qas.exclude(question_id__in=selected_set)
                          .order_by("last_attempted")
                          .values_list("question_id", flat=True)[:need]
            )
            selected.extend(recent_any_ids)
            selected_set.update(recent_any_ids)

    # Extreme edge-case: base_qs smaller than total_n
    need = total_n - len(selected)
    if need > 0:
        forced_ids = list(
            base_qs.exclude(id__in=selected_set)
                   .values_list("id", flat=True)[:need]
        )
        selected.extend(forced_ids)
        selected_set.update(forced_ids)

    final_ids = selected[:total_n]
    rnd.shuffle(final_ids)
    return list(Question.objects.filter(id__in=final_ids))

@login_required
def start_test(request):

    if request.method != "POST":
        return redirect("dashboard")

    user  = request.user
    ttype = request.POST.get("type")

    # ── 0. global guard ───────────────────────────────────────────────
    if Test.objects.filter(user=user, status="pending").count() >= 2:
        messages.warning(request, "You already have a pending test. Finish it before starting a new one.")
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

        questions_qs = Question.objects.filter(exam_name=exam.name, year=year).order_by("id")
        if not questions_qs.exists():
            messages.error(request, "No questions found for that exam & year.")
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        questions = list(questions_qs)  # fixed paper
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

        # IMPORTANT: adapt these filters to your schema:
        # - allowed exams (CSE/CAPF/CDS) could be exam_name__in or exams__name__in
        allowed_exams = ["CSE Prelims", "CAPF", "CDS"]

        base_qs = (
            Question.objects
            .filter(subject_id=subject_id)
            .filter(exam_name__in=allowed_exams)   # <-- change if M2M
            # .filter(qclass__in=["PYQ", "A", "B"]) # <-- if you have class/variant filtering
            .distinct()
        )

        print(base_qs.count())

        if not base_qs.exists():
            messages.error(request, "No questions found for that subject with selected filters.")
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        questions = select_questions_topic_smart(
            user=user,
            base_qs=base_qs,
            total_n=100,
            wrong_ratio=0.10,
            subject=subject,
            
            
            seed=None,               # or seed=timezone.now().date().toordinal()
        )

        if not questions:
            messages.error(request, "No questions found for that subject.")
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        test_name = f"{subject.name} – Subject Test"
        test_type = "full_length"
        year      = None
        exam      = None

    elif ttype == "section":
        section_id = int(request.POST["section"])
        section    = get_object_or_404(Section, pk=section_id)

        template, _ = TestTemplate.objects.get_or_create(
            user=user,
            section_id=section_id,
            exam=None,
            year=None,
            subject=None,
        )

        allowed_exams = ["CSE Prelims", "CAPF", "CDS"]

        base_qs = (
            Question.objects
            .filter(section_id=section_id)
            .filter(exam_name__in=allowed_exams)   # <-- change if M2M
            # .filter(qclass__in=["PYQ", "A", "B"])
            .distinct()
        )

        if not base_qs.exists():
            messages.error(request, "No questions found for that section with selected filters.")
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        questions = select_questions_topic_smart(
            user=user,
            base_qs=base_qs,
            total_n=50,
            wrong_ratio=0.10,
            section=section,
            
           
            seed=None,
        )

        if not questions:
            messages.error(request, "No questions found for that section.")
            return _hx_redirect_or_normal(request, reverse("dashboard"))

        test_name = f"{section.name} – Section Test"
        test_type = "sectional"
        year      = None
        exam      = None

    else:
        messages.error(request, "Invalid test type.")
        return _hx_redirect_or_normal(request, reverse("dashboard"))

    # ── 2. resume if template already has pending test ────────────────
    pending = Test.objects.filter(user=user, template=template, status="pending").first()
    if pending:
        if ttype == "exam_year":
            msg = f"You already have a pending test for {exam.name} {year}."
        elif ttype == "subject":
            msg = f"You already have a pending test for {subject.name}."
        elif ttype == "section":
            msg = f"You already have a pending test for {section.name}."
        else:
            msg = "You already have a pending test."

        messages.warning(request, msg)
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
            total_questions=len(questions),
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
    return _hx_redirect_or_normal(request, redirect_url)



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

# @login_required
# def start_test(request):
    
#     if request.method != "POST":
#         return redirect("dashboard")

#     user  = request.user
#     ttype = request.POST.get("type")    
    
    

#     # ── 0. global guard ───────────────────────────────────────────────
#     if Test.objects.filter(user=user, status="pending").count() >= 2:
#         messages.warning(request, "You already have a pending test. "
#                                   "Finish it before starting a new one.")
#         print(1)
#         return _hx_redirect_or_normal(request, reverse("dashboard"))

#     # ── 1. branch-specific template & question set ────────────────────
#     if ttype == "exam_year":
#         exam_id = int(request.POST["exam"])
#         year    = int(request.POST["year"])
#         exam    = get_object_or_404(Exam, pk=exam_id)

#         template, _ = TestTemplate.objects.get_or_create(
#             user=user,
#             exam_id=exam_id,
#             year=year,
#             subject=None,
#             section=None,
#         )

#         questions = Question.objects.filter(exam_name=exam.name, year=year).order_by("id")
#         if not questions:
#             messages.error(request, "No questions found for that exam & year.")
            
#             print(exam.name)
#             return _hx_redirect_or_normal(request, reverse("dashboard"))

#         test_name = f"{exam.name} {year}"
#         test_type = "full_length"

#     elif ttype == "subject":
#         subject_id = int(request.POST["subject"])
#         subject    = get_object_or_404(Subject, pk=subject_id)

#         template, _ = TestTemplate.objects.get_or_create(
#             user=user,
#             subject_id=subject_id,
#             exam=None,
#             year=None,
#             section=None,
#         )

#         qs_all = Question.objects.filter(subject_id=subject_id)
#         questions = qs_all.order_by("?")[:100] if qs_all.count() > 100 else qs_all.order_by("id")
#         if not questions:
#             messages.error(request, "No questions found for that subject.")
#             print(3)
#             return _hx_redirect_or_normal(request, reverse("dashboard"))

#         test_name = f"{subject.name} – Subject Test"
#         test_type = "full_length"
#         year      = None  # not used for subject tests
#         exam      = None

#     elif ttype == "section":
#         section_id = int(request.POST["section"])
#         section    = get_object_or_404(Section, pk=section_id)

#         template, _ = TestTemplate.objects.get_or_create(
#             user=user,
#             section_id=section_id,
#             exam=None,
#             year=None,
#             subject=None,
#         )

#         qs_all = Question.objects.filter(section_id=section_id)
#         questions = qs_all.order_by("?")[:50] if qs_all.count() > 50 else qs_all.order_by("id")
#         if not questions:
#             messages.error(request, "No questions found for that subject.")
            
#             return _hx_redirect_or_normal(request, reverse("dashboard"))

#         test_name = f"{section.name} – Section Test"
#         test_type = "sectional"
#         year      = None  # not used for subject tests
#         exam      = None

#     else:
#         messages.error(request, "Invalid test type.")
#         print(4)
#         return _hx_redirect_or_normal(request, reverse("dashboard"))

#     # ── 2. resume if template already has pending test ────────────────
#     pending = Test.objects.filter(user=user, template=template, status="pending").first()
#     if pending:
#         if ttype == "exam_year":
#             msg = f"You already have a pending test for {exam.name} {year}."
#         elif ttype == "subject":
#             msg = f"You already have a pending test for {subject.name}."
#         elif ttype == "section":
#             msg = f"You already have a pending test for {section.name}."
        
#         messages.warning(request, msg)        
#         return _hx_redirect_or_normal(request, reverse("dashboard"))
        

#     # ── 3. create Test & logs atomically ──────────────────────────────
#     with transaction.atomic():
#         serial = template.no_of_attempts + 1

#         test = Test.objects.create(
#             user=user,
#             template=template,
#             attempt_serial=serial,
#             name=test_name,
#             test_type=test_type,
#             exam=str(exam) if exam else None,
#             year=year,
#             total_questions=questions.count(),
#             start_time=timezone.now(),
#             status="pending",
#         )

#         QuestionLog.objects.bulk_create(
#             [
#                 QuestionLog(user=user, question=q, test=test, serial=i)
#                 for i, q in enumerate(questions, start=1)
#             ],
#             batch_size=500,
#         )

#         template.no_of_attempts = serial
#         template.save(update_fields=["no_of_attempts"])

#     # ── 4. send user to first question ────────────────────────────────
#     redirect_url = reverse("take_test", args=[test.id, 1])
#     print(6)           # ✅
#     return _hx_redirect_or_normal(request, redirect_url)


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
