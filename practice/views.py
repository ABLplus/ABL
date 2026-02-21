from django.shortcuts   import render, get_object_or_404, redirect
from django.http        import HttpResponse
from .models            import PracticeSession
from syllabus.models    import Subject, Section, Topic, SubTopic
from question.models     import OLT, Question
from tests.models         import QuestionLog, TopicAttemptSummary
from django.contrib.auth.decorators import login_required
import random
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q, F, Sum, Min, Max, Prefetch
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from collections import Counter
from analysis.models import TopicStatus
from django.conf import settings
from django.contrib.auth import get_user_model
from user.models import UserDailyStats, UserOverallStats

User = get_user_model()

    
@login_required
def create_practice(request):
    """
    • GET ?topic=<id>       – quick-start a topic session.
    • POST full filter form – subject / section / topic / subtopic / OLT.
    """
    user = request.user

    # --- 0. Guard: at most 2 pending sessions ------------------------
    if PracticeSession.objects.filter(user=user, status="pending").count() >= 2:
        messages.warning(request, "You already have two active practice sessions.")
        return redirect("dashboard")

    # ----------------------------------------------------------------
    # 1. Extract IDs (GET or POST)
    # ----------------------------------------------------------------
    data = request.GET if request.method == "GET" else request.POST

    subject_id  = data.get("subject")
    section_id  = data.get("section")
    topic_id    = data.get("topic")
    order_mode  = data.get("order", "serial")


    if PracticeSession.objects.filter(user=user, topic=topic_id,  status="pending").exists():
        messages.warning(request, "You already have active practice sessions of this topic.")
        return redirect("dashboard")

    # ----------------------------------------------------------------
    # 2. If only topic is given, derive its parents
    # ----------------------------------------------------------------
    if topic_id and not subject_id:
        topic_obj   = get_object_or_404(Topic, pk=topic_id)
        section_obj = topic_obj.section
        subject_obj = section_obj.subject
        # override IDs
        subject_id = subject_obj.id
        section_id = section_obj.id
    else:
        topic_obj   = None  # will fetch later if needed

    # ----------------------------------------------------------------
    # 3. Resolve objects (safe if None)
    # ----------------------------------------------------------------
    subject  = get_object_or_404(Subject, pk=subject_id)   if subject_id  else None
    section  = get_object_or_404(Section, pk=section_id)   if section_id  else None
    topic    = topic_obj or (get_object_or_404(Topic, pk=topic_id) if topic_id else None)



    # Need at least a topic to form a session
    if not topic:
        messages.error(request, "Please select a topic to start practice.")
        return redirect("dashboard")

    # ----------------------------------------------------------------
    # 4. Build question queryset – deepest filter wins
    # ----------------------------------------------------------------
    qs = Question.objects.filter(topic=topic)


    if PracticeSession.objects.filter(user=user, topic=topic).count() > 1:
        order_mode = "random"


    ids = list(qs.values_list("id", flat=True))
    if order_mode == "random":
        random.shuffle(ids)
    else:  # serial = newest first
        ids.sort(reverse=True)

    if len(ids) < 4:
        messages.error(request, "Not enough questions for that filter.")
        return redirect("dashboard")

    # ----------------------------------------------------------------
    # 5. Create session + logs atomically
    # ----------------------------------------------------------------
    with transaction.atomic():
        session = PracticeSession.objects.create(
            user=user,
            subject=subject,
            section=section,
            topic=topic,
            status="pending",
            total_questions=len(ids),
            start_time=timezone.now(),
        )

        QuestionLog.objects.bulk_create([
            QuestionLog(
                user=user,
                question_id=qid,
                practiceSession=session,
                serial=idx,
                attempt_type="unattempted",
            )
            for idx, qid in enumerate(ids, start=1)
        ])

    return redirect("practice:take_practice", session.id)
# ── PAGE LOAD : take_practice ───────────────────────────────────────────────
@login_required
def take_practice(request, session_id):
    session = get_object_or_404(
        PracticeSession, id=session_id, user=request.user
    )

    first_log = (
        session.questionlog_set
        .filter(user_answered__isnull=True)
        .order_by("serial")
        .first()
        or session.questionlog_set.order_by("serial").first()
    )

    return render(
        request,
        "practice/take_practice.html",
        {
            "session":      session,
            "first_serial": first_log.serial if first_log else 1,
        },
    )

# ── HTMX ENDPOINT : question card / result / nav ────────────────────────────
@login_required
def practice_question_htmx(request, session_id, serial):
    session = get_object_or_404(
        PracticeSession, id=session_id, user=request.user
    )
    qlog = get_object_or_404(
        QuestionLog, practiceSession=session, serial=serial
    )
    
    # ---------- POST  : save answer -----------------------------------------
    if request.method == "POST":
        user_answered = request.POST.get("option")
        attempt_type  = request.POST.get("attempt_type")

        if not qlog.user_answered:                       # ensure only first save
            qlog.user_answered = user_answered
            qlog.attempt_type  = attempt_type
            qlog.timestamp     = timezone.now()
            qlog.attempt_result = (
                "right"
                if user_answered
                and user_answered.lower() == qlog.question.correct_option.lower()
                else "wrong"
            )
            qlog.save()

        # next *unattempted* question
        next_log = (
            session.questionlog_set
            .filter(user_answered__isnull=True, serial__gt=serial)
            .order_by("serial")
            .first()
        )

        # ----------- nothing left  →  COMPLETE SESSION ----------------------
        if not next_log:            
            _finalise_session_and_update_summary(session)

            return render(
                request,
                "practice/partials/question_result.html",
                {
                    "qlog": qlog,
                    "next_log": None,                  # important to hide next button
                    "prev_serial": serial - 1,

                },
            )

        # Otherwise return result + next button
        return render(
            request,
            "practice/partials/question_result.html",
            {"qlog": qlog, "next_log": next_log, "prev_serial": serial - 1},
        )

    # ---------- GET : navigation / first load -------------------------------
    prev_serial = serial - 1 if serial > 1 else None
    next_log_any = (
        session.questionlog_set
        .filter(serial__gt=serial)
        .order_by("serial")
        .first()
    )

    if qlog.user_answered:                                 
        
        # already attempted → show result / explanation
        return render(
            request,
            "practice/partials/question_result.html",
            {
                "qlog":      qlog,
                "next_log":  next_log_any,
                "prev_serial": prev_serial,
            },
        )
    # not attempted yet → normal question card
    return render(
        request,
        "practice/partials/question_card.html",
        {
            "qlog":      qlog,
            "prev_serial": prev_serial,
        },
    )

# PMI computation utility
def _compute_and_update_topic_pmi(user, topic, *, newly_completed_session_id=None):
    """
    Compute PMI over the last N completed practice sessions for (user, topic)
    and persist on TopicStatus.pmi as a percentage.

    Rules:
      - Only last N sessions (default N=3 via ABL_PMI_WINDOW) are considered
        for the PMI window.
      - PMI can be negative (penalties > rewards).
      - PMI is capped at 100 on the upper side (no lower clamp).
      - If only 1 session in *window*, cap positive PMI at 55% (negatives allowed).
      - Also store TopicStatus.subject, TopicStatus.section, TopicStatus.exam
        from Topic.
    """
    N = getattr(settings, "ABL_PMI_WINDOW", 3)
    print(f"Computing PMI for user={user}, topic={topic}, window={N}")

    # Base queryset: all completed sessions for that user+topic
    base_qs = PracticeSession.objects.filter(
        user=user,
        topic=topic,
        status="completed",
    )

    # If we are recomputing "historically" for a particular session,
    # restrict the window to sessions up to and including that one.
    if newly_completed_session_id is not None:
        try:
            anchor = PracticeSession.objects.get(
                id=newly_completed_session_id,
                user=user,
                topic=topic,
            )
            base_qs = base_qs.filter(end_time__lte=anchor.end_time)
        except PracticeSession.DoesNotExist:
            # If something is off, just fall back to all completed sessions.
            pass

    base_qs = base_qs.order_by("-end_time")

    # Total completed sessions (lifetime) for practice_rounds
    total_session_count = base_qs.count()
    if total_session_count == 0:
        return

    # Last N session IDs (PMI window)
    recent_ids = list(base_qs.values_list("id", flat=True)[:N])
    window_session_count = len(recent_ids)
    print(f'window_session_count: {window_session_count}')
    if window_session_count == 0:
        return

    window_qs = PracticeSession.objects.filter(id__in=recent_ids)

    agg = window_qs.aggregate(
        S_a=Sum("sureshot_attempts"),
        A_a=Sum("applied_attempts"),
        G_a=Sum("guesswork_attempts"),

        S_w=Sum("sureshot_wrong"),
        A_w=Sum("applied_wrong"),
        G_w=Sum("guesswork_wrong"),
    )

    # Coalesce None → 0
    S_a = agg["S_a"] or 0
    A_a = agg["A_a"] or 0
    G_a = agg["G_a"] or 0

    S_w = agg["S_w"] or 0
    A_w = agg["A_w"] or 0
    G_w = agg["G_w"] or 0

    # Rights (guard against negatives)
    S_r = max(S_a - S_w, 0)
    A_r = max(A_a - A_w, 0)
    G_r = max(G_a - G_w, 0)

    denom = S_a + A_a + G_a
    print(f"Denom: {denom}, S_r: {S_r}, A_r: {A_r}, G_r: {G_r}, S_w: {S_w}, A_w: {A_w}, G_w: {G_w}")


    if denom <= 0:
        pmi_pct = 0.0
    else:
        # PMI_raw = ((Sr*2 + Ar*1.5 + Gr*0.75) - (Sw*0.75 + Aw*0.5)) / denom * 2
        reward = S_r * 2.0 + A_r * 1.5 + G_r * 0.75
        print(f"Reward: {reward}")
        penalty = S_w * 0.75 + A_w * 0.5
        print(f"Penalty: {penalty}")
        pmi_raw = ((reward - penalty) / (denom * 2.0)) 

        # Convert to percentage: allow negative, cap upper at 100
        pmi_pct = pmi_raw * 100.0
        if pmi_pct > 100.0:
            pmi_pct = 100.0

        # First-session-in-window positive cap at 55%
        # (matches the rule: "If only 1 session in window...")
        if window_session_count == 1 and pmi_pct > 55.0:
            pmi_pct = 55.0

    # Pull subject/section from the topic
    section = topic.section
    subject = section.subject
    exam = subject.exam

    # Upsert TopicStatus (stable identifiers only: user+topic)
    topic_status, _ = TopicStatus.objects.get_or_create(
        user=user,
        topic=topic,
        defaults={
            "pmi": pmi_pct,
            # store *total* completed practice rounds, not just window
            "practice_rounds": total_session_count,
            "section": section,
            "subject": subject,
            "exam": exam,
        },
    )

    # Update dynamic fields
    print(
        f"PMI for {user.username} / {topic.name} updated to "
        f"{pmi_pct:.2f} over last {window_session_count} sessions "
        f"(total={total_session_count})"
    )

    topic_status.pmi = pmi_pct

    if hasattr(topic_status, "practice_rounds"):
        topic_status.practice_rounds = total_session_count
    if hasattr(topic_status, "section"):
        topic_status.section = section
    if hasattr(topic_status, "subject"):
        topic_status.subject = subject
    if hasattr(topic_status, "exam"):
        topic_status.exam = exam

    # Optional timestamps if not auto-managed
    if hasattr(topic_status, "updated_at"):
        topic_status.updated_at = timezone.now()

    topic_status.save()

# ── FINALISE SESSION & UPDATE SUMMARY ─────────────────────────────────────

def _finalise_session_and_update_summary(session: PracticeSession) -> None:
    """
    Populate PracticeSession stats **and** update:
      1) TopicAttemptSummary (mode=practice)
      2) UserDailyStats (today)
      3) UserOverallStats (JSON buckets)
      4) TopicStatus.pmi recompute

    All in ONE atomic transaction, using ONE aggregation over QuestionLogs.
    """
    # Guard: prevent double counting
    if session.status == "completed":
        return

    logs = session.questionlog_set.all()

    # Aggregate once – cheap & accurate
    agg = logs.aggregate(
        total_q         = Count("id"),
        answered_q      = Count("id", filter=Q(user_answered__isnull=False)),
        correct_q       = Count("id", filter=Q(attempt_result="right")),

        sureshot_q      = Count("id", filter=Q(attempt_type="sureshot")),
        applied_q       = Count("id", filter=Q(attempt_type="applied")),
        guesswork_q     = Count("id", filter=Q(attempt_type="guesswork")),

        sureshot_wrong  = Count("id", filter=Q(attempt_type="sureshot",  attempt_result="wrong")),
        applied_wrong   = Count("id", filter=Q(attempt_type="applied",   attempt_result="wrong")),
        guesswork_wrong = Count("id", filter=Q(attempt_type="guesswork", attempt_result="wrong")),
    )

    total_q     = int(agg.get("total_q") or 0)
    answered_q  = int(agg.get("answered_q") or 0)
    correct_q   = int(agg.get("correct_q") or 0)
    wrong_q     = max(0, answered_q - correct_q)

    sureshot_q  = int(agg.get("sureshot_q") or 0)
    applied_q   = int(agg.get("applied_q") or 0)
    guesswork_q = int(agg.get("guesswork_q") or 0)

    sureshot_wrong  = int(agg.get("sureshot_wrong") or 0)
    applied_wrong   = int(agg.get("applied_wrong") or 0)
    guesswork_wrong = int(agg.get("guesswork_wrong") or 0)

    # Net mark rule (+2 / −0.66). Keep consistent with your platform.
    net_marks = (correct_q * 2.0) - (wrong_q * 0.66)

    # Time add rule: cap inflated session time
    end_ts = timezone.now()

    actual_seconds = 0
    if session.start_time:
        actual_seconds = max(0, int((end_ts - session.start_time).total_seconds()))
    actual_hours = actual_seconds / 3600.0

    expected_minutes = total_q * 2.0
    expected_hours = expected_minutes / 60.0
    max_allowed_hours = expected_hours * 1.25

    if expected_hours > 0 and actual_hours > max_allowed_hours:
        hours_to_add = expected_hours
    else:
        hours_to_add = actual_hours

    hours_to_add = float(round(hours_to_add, 4))

    stats_date = timezone.localdate()
    mode = "practice"

    # Helper for JSON-field increments in UserOverallStats
    def _inc_json(d: dict, key: str, add: int) -> dict:
        if not isinstance(d, dict):
            d = {}
        d.setdefault("practice", 0)
        d.setdefault("test", 0)
        d[key] = int(d.get(key, 0) or 0) + int(add or 0)
        return d

    with transaction.atomic():
        # ── update PracticeSession ────────────────────────────────────────────
        session.total_questions    = total_q
        session.correct_answers    = correct_q
        session.total_score        = net_marks

        session.sureshot_attempts  = sureshot_q
        session.applied_attempts   = applied_q
        session.guesswork_attempts = guesswork_q

        session.sureshot_wrong     = sureshot_wrong
        session.applied_wrong      = applied_wrong
        session.guesswork_wrong    = guesswork_wrong

        session.status             = "completed"
        session.end_time           = end_ts
        session.save()

        # ── upsert UserDailyStats ────────────────────────────────────────────
        uds, _ = UserDailyStats.objects.get_or_create(
            user=session.user,
            date=stats_date,
            defaults={
                "practice_sessions": 0,
                "test_sessions": 0,
                "total_attempts": 0,
                "total_correct": 0,
                "total_wrong": 0,
                "sureshot_attempts": 0,
                "applied_attempts": 0,
                "guesswork_attempts": 0,
                "sureshot_wrong": 0,
                "applied_wrong": 0,
                "guesswork_wrong": 0,
                "practice_time": 0.0,
                "test_time": 0.0,
            },
        )

        UserDailyStats.objects.filter(pk=uds.pk).update(
            practice_sessions=F("practice_sessions") + 1,

            total_attempts=F("total_attempts") + answered_q,
            total_correct=F("total_correct") + correct_q,
            total_wrong=F("total_wrong") + wrong_q,

            sureshot_attempts=F("sureshot_attempts") + sureshot_q,
            applied_attempts=F("applied_attempts") + applied_q,
            guesswork_attempts=F("guesswork_attempts") + guesswork_q,

            sureshot_wrong=F("sureshot_wrong") + sureshot_wrong,
            applied_wrong=F("applied_wrong") + applied_wrong,
            guesswork_wrong=F("guesswork_wrong") + guesswork_wrong,

            practice_time=F("practice_time") + hours_to_add,
        )

        # ── update UserOverallStats (JSON buckets per mode) ──────────────────
        ous, _ = UserOverallStats.objects.select_for_update().get_or_create(user=session.user)

        ous.total_attempts = _inc_json(ous.total_attempts, mode, answered_q)
        ous.total_correct  = _inc_json(ous.total_correct,  mode, correct_q)
        ous.total_wrong    = _inc_json(ous.total_wrong,    mode, wrong_q)

        ous.sureshot_attempts  = _inc_json(ous.sureshot_attempts,  mode, sureshot_q)
        ous.applied_attempts   = _inc_json(ous.applied_attempts,   mode, applied_q)
        ous.guesswork_attempts = _inc_json(ous.guesswork_attempts, mode, guesswork_q)

        ous.sureshot_wrong  = _inc_json(ous.sureshot_wrong,  mode, sureshot_wrong)
        ous.applied_wrong   = _inc_json(ous.applied_wrong,   mode, applied_wrong)
        ous.guesswork_wrong = _inc_json(ous.guesswork_wrong, mode, guesswork_wrong)

        ous.save()

        # ── upsert TopicAttemptSummary (mode=practice) ───────────────────────
        summary, _ = TopicAttemptSummary.objects.get_or_create(
            user=session.user,
            topic=session.topic,
            mode="practice",
            defaults={
                "total_attempts": 0,
                "correct_attempts": 0,
                "wrong_attempts": 0,
                "net_marks": 0,
                "sureshot_attempts": 0,
                "applied_attempts": 0,
                "guesswork_attempts": 0,
                "sureshot_wrong": 0,
                "applied_wrong": 0,
                "guesswork_wrong": 0,
            },
        )

        TopicAttemptSummary.objects.filter(pk=summary.pk).update(
            total_attempts=F("total_attempts") + answered_q,
            correct_attempts=F("correct_attempts") + correct_q,
            wrong_attempts=F("wrong_attempts") + wrong_q,

            sureshot_attempts=F("sureshot_attempts") + sureshot_q,
            applied_attempts=F("applied_attempts") + applied_q,
            guesswork_attempts=F("guesswork_attempts") + guesswork_q,

            sureshot_wrong=F("sureshot_wrong") + sureshot_wrong,
            applied_wrong=F("applied_wrong") + applied_wrong,
            guesswork_wrong=F("guesswork_wrong") + guesswork_wrong,

            net_marks=F("net_marks") + net_marks,
        )

        # ── recompute TopicStatus.pmi from last-N sessions ───────────────────
        _compute_and_update_topic_pmi(session.user, session.topic)

        # Optional: profile counters (keep if you use it)
        session.user.profile.register_attempt(increment=answered_q)

# def _finalise_session_and_update_summary(session: PracticeSession) -> None:
#     """
#     Populate PracticeSession stats **and** upsert TopicAttemptSummary
#     in ONE atomic transaction. Also recompute TopicStatus.pmi using last-N sessions.
#     """
#     logs = session.questionlog_set.all()

#     # Aggregate once – cheaper & 100 % accurate
#     agg = logs.aggregate(
#         total_q         = Count("id"),
#         answered_q      = Count("id", filter=Q(user_answered__isnull=False)),
#         correct_q       = Count("id", filter=Q(attempt_result="right")),
#         sureshot_q      = Count("id", filter=Q(attempt_type="sureshot")),
#         applied_q       = Count("id", filter=Q(attempt_type="applied")),
#         guesswork_q     = Count("id", filter=Q(attempt_type="guesswork")),

#         sureshot_wrong  = Count("id", filter=Q(attempt_type="sureshot", attempt_result="wrong")),
#         applied_wrong   = Count("id", filter=Q(attempt_type="applied",  attempt_result="wrong")),
#         guesswork_wrong = Count("id", filter=Q(attempt_type="guesswork",attempt_result="wrong")),
#     )

#     wrong_q      = (agg["answered_q"] or 0) - (agg["correct_q"] or 0)
    

#     # Simple net-mark rule (+2 / −0.66) – tweak if you use a different formula
#     net_marks = ((agg["correct_q"] or 0) * 2.0) - (wrong_q * 0.66)

#     attempt_count = agg["answered_q"] or 0

#     with transaction.atomic():
#         # ── update PracticeSession ────────────────────────────────────────────
#         session.total_questions   = agg["total_q"] or 0
#         session.correct_answers   = agg["correct_q"] or 0
        
#         session.total_score       = net_marks

#         session.sureshot_attempts = agg["sureshot_q"] or 0
#         session.applied_attempts  = agg["applied_q"] or 0
#         session.guesswork_attempts= agg["guesswork_q"] or 0

#         session.sureshot_wrong    = agg["sureshot_wrong"] or 0
#         session.applied_wrong     = agg["applied_wrong"] or 0
#         session.guesswork_wrong   = agg["guesswork_wrong"] or 0

#         session.status            = "completed"
#         session.end_time          = timezone.now()
#         session.save()

#         # ── upsert TopicAttemptSummary ───────────────────────────────────────
#         summary, _ = TopicAttemptSummary.objects.get_or_create(
#             user  = session.user,
#             topic = session.topic,
#             mode  = "practice",
#             defaults = {
#                 "total_attempts":   0,
#                 "correct_attempts": 0,
#                 "wrong_attempts":   0,
#                 "net_marks":        0,
#                 "sureshot_attempts": 0,
#                 "applied_attempts":  0,
#                 "guesswork_attempts":0,
#                 "sureshot_wrong":    0,
#                 "applied_wrong":     0,
#                 "guesswork_wrong":   0,
#             },
#         )

#         # increment counters from this session
#         summary.total_attempts      = F("total_attempts")      + (agg["answered_q"] or 0)
#         summary.correct_attempts    = F("correct_attempts")    + (agg["correct_q"] or 0)
#         summary.wrong_attempts      = F("wrong_attempts")      + wrong_q

#         summary.sureshot_attempts   = F("sureshot_attempts")   + (agg["sureshot_q"] or 0)
#         summary.applied_attempts    = F("applied_attempts")    + (agg["applied_q"] or 0)
#         summary.guesswork_attempts  = F("guesswork_attempts")  + (agg["guesswork_q"] or 0)

#         summary.sureshot_wrong      = F("sureshot_wrong")      + (agg["sureshot_wrong"] or 0)
#         summary.applied_wrong       = F("applied_wrong")       + (agg["applied_wrong"] or 0)
#         summary.guesswork_wrong     = F("guesswork_wrong")     + (agg["guesswork_wrong"] or 0)

#         summary.net_marks           = F("net_marks")           + net_marks
#         summary.save()

#         # ── recompute TopicStatus.pmi from last-N sessions (emergent trend) ──
#         _compute_and_update_topic_pmi(session.user, session.topic)
        
#         # Optional: streaks / profile counters
#         session.user.profile.register_attempt(increment=attempt_count)

        


# ── SUMMARY PAGE (simple) ─────────────────────────────────────
@login_required
def practice_summary(request, session_id):
    """
    Practice session summary with filters:
      - result: right|wrong
      - attempt_type: sureshot|applied|guesswork
    """
    session = get_object_or_404(PracticeSession, id=session_id, user=request.user)

    PENDING  = "pending"
    COMPLETE = "completed"

    next_log = (
        session.questionlog_set
        .filter(user_answered__isnull=True)
        .order_by("serial")
        .first()
    )
    if session.status == PENDING:
        if next_log is None:
            _finalise_session_and_update_summary(session)
            session.refresh_from_db()
        else:
            return redirect("dashboard")

    # ---------- NEW: compute session-level stats (Practice mode; no blind) ----------
    total_qs = session.total_questions or 0
    attempts = max(total_qs, 0)
    right    = session.correct_answers or 0
    wrong    = max(attempts - right, 0)

    ss_attempts      = session.sureshot_attempts or 0
    ss_wrong         = session.sureshot_wrong or 0

    applied_attempts = session.applied_attempts or 0
    applied_wrong    = session.applied_wrong or 0

    guess_attempts   = session.guesswork_attempts or 0
    guess_wrong      = session.guesswork_wrong or 0

    session_stats = {
        "total_qs": total_qs,
        "right": right,
        "wrong": wrong,

        "ss_attempts": ss_attempts,
        "ss_wrong": ss_wrong,
        "ss_wrong_pct": _pct(ss_wrong, ss_attempts),
        "ss_attempt_pct": _pct(ss_attempts, attempts),

        "applied_attempts": applied_attempts,
        "applied_wrong": applied_wrong,
        "applied_wrong_pct": _pct(applied_wrong, applied_attempts),
        "applied_attempt_pct": _pct(applied_attempts, attempts),

        "guess_attempts": guess_attempts,
        "guess_wrong": guess_wrong,
        "guess_wrong_pct": _pct(guess_wrong, guess_attempts),
        "guess_attempt_pct": _pct(guess_attempts, attempts),

        "overall_wrong_pct": _pct(wrong, attempts),
    }
    # ---------- END NEW ----------

    # ✅ Always initialize logs_qs BEFORE filtering
    logs_qs = session.questionlog_set.select_related("question__subject")

    # --- Filters ------------------------------------------------------
    selected_result = request.GET.get("result") or ""
    if selected_result in ("right", "wrong"):
        logs_qs = logs_qs.filter(attempt_result=selected_result)
    else:
        selected_result = ""

    selected_attempt_type = request.GET.get("attempt_type") or ""
    if selected_attempt_type in ("sureshot", "applied", "guesswork"):
        logs_qs = logs_qs.filter(attempt_type=selected_attempt_type)
    else:
        selected_attempt_type = ""

    logs = list(logs_qs.order_by("serial"))

    subject_counter = Counter(
        [log.question.subject.name for log in logs if getattr(log.question, "subject", None)]
    )
    subjects = [{"name": name, "count": count} for name, count in sorted(subject_counter.items())]

    selected_subject = request.GET.get("subject") or ""
    if not selected_subject and len(subjects) == 1:
        selected_subject = subjects[0]["name"]

    if selected_subject:
        logs = [l for l in logs if l.question.subject and l.question.subject.name == selected_subject]

    context = {
        "session": session,
        "logs": logs,
        "log_count": len(logs),
        "subjects": subjects,
        "selected_subject": selected_subject,
        "selected_result": selected_result,
        "selected_attempt_type": selected_attempt_type,

        # NEW
        "session_stats": session_stats,
    }
    return render(request, "practice/practice_summary.html", context)

@login_required
def history_page(request):
    sessions = PracticeSession.objects.filter(user=request.user).order_by("-end_time")
    page_obj  = Paginator(sessions, 5).get_page(request.GET.get("page", 1))
    return render(request,
                  "practice/partials/history_rows.html",
                  {"page_obj": page_obj})

# ——— HTMX endpoints for chained selects ———
@login_required
def ajax_load_sections(request):
    subject_id = request.GET.get("subject")
    if subject_id and subject_id != "none":
        secs = Section.objects.filter(subject_id=subject_id).order_by("name")
    else:
        secs = Section.objects.none()
    return render(request, "practice/partials/section_options.html", {
        "sections": secs
    })

@login_required
def ajax_load_topics(request):
    section_id = request.GET.get("section")
    if section_id and section_id != "none":
        tops = Topic.objects.filter(section_id=section_id).order_by("name")
    else:
        tops = Topic.objects.none()
    return render(request, "practice/partials/topic_options.html", {
        "topics": tops
    })

@login_required
def ajax_load_subtopics(request):
    topic_id = request.GET.get("topic")
    if topic_id and topic_id != "none":
        subs = SubTopic.objects.filter(topic_id=topic_id).order_by("name")
    else:
        subs = SubTopic.objects.none()
    return render(request, "practice/partials/subtopic_options.html", {
        "subtopics": subs
    })

@login_required
def ajax_subject_tree(request, subject_id):
    """
    HTMX endpoint that returns the collapsible subject → section → topic tree
    for the sidebar / modal. Optimized to avoid N+1 queries by prefetching
    TopicAttemptSummary objects filtered for the current user in 'practice' mode.
    """

    # Prefetch summaries for this user and mode
    subject = get_object_or_404(
        Subject.objects.prefetch_related(
            Prefetch(
                "sections__topics__topicattemptsummary_set",
                queryset=TopicAttemptSummary.objects.filter(
                    user=request.user, mode="practice"
                ),
                to_attr="practice_summaries",   # summaries now available as list
            ),
            "sections__topics__subtopics",
        ),
        pk=subject_id,
    )

    sections_data = []
    for section in subject.sections.all():
        topics_data = []
        for topic in section.topics.all():
            # summaries were pre-attached by Prefetch
            summary = topic.practice_summaries[0] if topic.practice_summaries else None

            if summary and summary.total_attempts:
                accuracy  = summary.accuracy
                wrong_pct = round(summary.wrong_rate, 1)

                if accuracy > 80:
                    color = "green"
                elif 50 <= accuracy <= 80:
                    color = "orange"
                else:
                    color = "red"
            else:
                wrong_pct = None
                color = "grey"

            topics_data.append({
                "id":        topic.id,
                "name":      topic.name,
                "color":     color,
                "wrong_pct": wrong_pct,
                "subtopics": [
                    {"id": sub.id, "name": sub.name}
                    for sub in topic.subtopics.all()
                ],
            })

        sections_data.append({
            "name":   section.name,
            "topics": topics_data,
        })

    return render(
        request,
        "practice/partials/subject_tree.html",
        {"sections": sections_data},
    )

def _pct(part, whole):
    try:
        return (float(part) / float(whole) * 100.0) if whole else 0.0
    except ZeroDivisionError:
        return 0.0


@login_required
def ajax_subject_sections(request, subject_id):
    """
    Return an HTMX fragment with all Sections that belong to a Subject.
    Called by the Capsule-Practice accordion in practice_home.html.
    """
    subject  = get_object_or_404(Subject, pk=subject_id)
    sections = subject.sections.all()   # or Section.objects.filter(subject=subject)

    return render(
        request,
        "practice/partials/subject_sections.html",    # see next file
        {
            "subject": subject,
            "sections": sections,
        },
    )

# ── MODAL CONTENT ENDPOINTS ────────────────────────────────────────────────
@login_required
def subject_modal(request, subject_id):
    subject = get_object_or_404(Subject, pk=subject_id)
    return render(request, "practice/partials/subject_modal.html", {"subject": subject})

@login_required
def section_modal(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    return render(request, "practice/partials/section_modal.html", {"section": section})

@login_required
def topic_modal(request, topic_id):
    user = request.user
    topic = get_object_or_404(Topic, pk=topic_id)

    sessions_qs = (
        PracticeSession.objects
        .filter(user=user, topic=topic)
        .order_by("start_time")
    )

    session_rows = []
    for idx, s in enumerate(sessions_qs, start=1):
        total_qs = s.total_questions or 0
        attempts = max(total_qs, 0)
        right    = s.correct_answers or 0
        wrong    = max(attempts - right, 0)

        ss_attempts      = s.sureshot_attempts or 0
        ss_wrong         = s.sureshot_wrong or 0
        applied_attempts = s.applied_attempts or 0
        applied_wrong    = s.applied_wrong or 0
        guess_attempts   = s.guesswork_attempts or 0
        guess_wrong      = s.guesswork_wrong or 0

        session_rows.append({
            "id": s.id,
            "round_num": idx,
            "start_time": s.start_time,
            "end_time": s.end_time,

            "total_qs": total_qs,
            "right": right,
            "wrong": wrong,

            # x/y (z%) for each type
            "ss_attempts": ss_attempts,
            "ss_wrong": ss_wrong,
            "ss_wrong_pct": _pct(ss_wrong, ss_attempts),

            "applied_attempts": applied_attempts,
            "applied_wrong": applied_wrong,
            "applied_wrong_pct": _pct(applied_wrong, applied_attempts),

            "guess_attempts": guess_attempts,
            "guess_wrong": guess_wrong,
            "guess_wrong_pct": _pct(guess_wrong, guess_attempts),

            # attempt distribution n% per type (denominator = total attempted)
            "ss_attempt_pct": _pct(ss_attempts, attempts),
            "applied_attempt_pct": _pct(applied_attempts, attempts),
            "guess_attempt_pct": _pct(guess_attempts, attempts),

            # overall % wrong (all attempts)
            "overall_wrong_pct": _pct(wrong, attempts),
        })

    if session_rows:
        agg = sessions_qs.aggregate(
            total_questions_sum   = Sum("total_questions"),
            correct_sum           = Sum("correct_answers"),

            sureshot_attempts_sum = Sum("sureshot_attempts"),
            applied_attempts_sum  = Sum("applied_attempts"),
            guess_attempts_sum    = Sum("guesswork_attempts"),

            sureshot_wrong_sum    = Sum("sureshot_wrong"),
            applied_wrong_sum     = Sum("applied_wrong"),
            guess_wrong_sum       = Sum("guesswork_wrong"),

            first_date            = Min("start_time"),
            last_date             = Max("end_time"),
            last_any_time         = Max("start_time"),
        )

        overall_total_qs = agg["total_questions_sum"] or 0
        overall_attempts = max(overall_total_qs, 0)
        overall_right    = agg["correct_sum"] or 0
        overall_wrong    = max(overall_attempts - overall_right, 0)

        overall_ss_attempts = agg["sureshot_attempts_sum"] or 0
        overall_ap_attempts = agg["applied_attempts_sum"] or 0
        overall_gw_attempts = agg["guess_attempts_sum"] or 0

        overall_ss_wrong = agg["sureshot_wrong_sum"] or 0
        overall_ap_wrong = agg["applied_wrong_sum"] or 0
        overall_gw_wrong = agg["guess_wrong_sum"] or 0

        overall = {
            "total_qs": overall_total_qs,
            "right": overall_right,
            "wrong": overall_wrong,

            "ss_attempts": overall_ss_attempts,
            "ss_wrong": overall_ss_wrong,
            "ss_wrong_pct": _pct(overall_ss_wrong, overall_ss_attempts),

            "applied_attempts": overall_ap_attempts,
            "applied_wrong": overall_ap_wrong,
            "applied_wrong_pct": _pct(overall_ap_wrong, overall_ap_attempts),

            "guess_attempts": overall_gw_attempts,
            "guess_wrong": overall_gw_wrong,
            "guess_wrong_pct": _pct(overall_gw_wrong, overall_gw_attempts),

            # attempt distribution across all practice_rounds (denominator = total attempted across rounds)
            "ss_attempt_pct": _pct(overall_ss_attempts, overall_attempts),
            "applied_attempt_pct": _pct(overall_ap_attempts, overall_attempts),
            "guess_attempt_pct": _pct(overall_gw_attempts, overall_attempts),

            "overall_wrong_pct": _pct(overall_wrong, overall_attempts),

            "first_date": agg["first_date"],
            "last_date":  agg["last_date"] or agg["last_any_time"],
        }

        last_updated = overall["last_date"]
    else:
        overall = None
        last_updated = None

    practice_url = reverse("practice:create_practice") + f"?topic={topic.id}"

    num_questions = getattr(topic, "num_questions", None)
    if num_questions is None:
        try:
            num_questions = topic.questions.count()
        except Exception:
            num_questions = None

    return render(
        request,
        "practice/partials/topic_modal.html",
        {
            "topic": topic,
            "session_rows": session_rows,
            "overall": overall,
            "last_updated": last_updated,
            "practice_url": practice_url,
            "num_questions": num_questions,
        },
    )

def modal_empty(request):
    # Returning empty clears the modal when swapped into #modal-root
    return HttpResponse("")

