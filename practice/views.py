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
from django.db.models import Count, Q, F
from collections import defaultdict
from decimal import Decimal
from django.contrib.auth.models import User
from django.http import JsonResponse







# ── Helper ──────────────────────────────────────────────────────────────────
def _finalise_session_and_update_summary(session: PracticeSession) -> None:
    """
    Populate PracticeSession stats **and** upsert TopicAttemptSummary
    in ONE atomic transaction.
    """
    logs = session.questionlog_set.all()

    # Aggregate once – cheaper & 100 % accurate
    agg = logs.aggregate(
        total_q         = Count("id"),
        answered_q      = Count("id", filter=Q(user_answered__isnull=False)),
        correct_q       = Count("id", filter=Q(attempt_result="right")),
        sureshot_q      = Count("id", filter=Q(attempt_type="sureshot")),
        applied_q       = Count("id", filter=Q(attempt_type="applied")),
        guesswork_q     = Count("id", filter=Q(attempt_type="guesswork")),
        blind_q         = Count("id", filter=Q(attempt_type="blind")),
        sureshot_wrong  = Count("id", filter=Q(attempt_type="sureshot", attempt_result="wrong")),
        applied_wrong   = Count("id", filter=Q(attempt_type="applied",  attempt_result="wrong")),
        guesswork_wrong = Count("id", filter=Q(attempt_type="guesswork",attempt_result="wrong")),
        blind_wrong     = Count("id", filter=Q(attempt_type="blind",    attempt_result="wrong")),
    )

    wrong_q      = agg["answered_q"] - agg["correct_q"]
    unattempted  = agg["total_q"]    - agg["answered_q"]

    # Simple net-mark rule (+2 / −0.66) – tweak if you use a different formula
    net_marks = (agg["correct_q"] * 2) - (wrong_q * 0.66)

    with transaction.atomic():                            # -------- NEW --------
        # ── update PracticeSession ────────────────────────────────────────────
        session.total_questions   = agg["total_q"]
        session.correct_answers   = agg["correct_q"]
        session.unattempted       = unattempted
        session.total_score       = net_marks

        session.sureshot_attempts = agg["sureshot_q"]
        session.applied_attempts  = agg["applied_q"]
        session.guesswork_attempts= agg["guesswork_q"]
        session.blind_attempts    = agg["blind_q"]

        session.sureshot_wrong    = agg["sureshot_wrong"]
        session.applied_wrong     = agg["applied_wrong"]
        session.guesswork_wrong   = agg["guesswork_wrong"]
        session.blind_wrong       = agg["blind_wrong"]

        session.status            = "completed"
        session.end_time          = timezone.now()
        session.save()

        # ── upsert TopicAttemptSummary ───────────────────────────────────────
        summary, _ = TopicAttemptSummary.objects.get_or_create(
            user  = session.user,
            topic = session.topic,
            mode  = "practice",
            defaults = {
                "total_attempts":   0,
                "correct_attempts": 0,
                "wrong_attempts":   0,
                "net_marks":        0,
            },
        )

        # update (add) current-session numbers
        summary.total_attempts   = F("total_attempts")   + agg["answered_q"]
        summary.correct_attempts = F("correct_attempts") + agg["correct_q"]
        summary.wrong_attempts   = F("wrong_attempts")   + wrong_q

        summary.sureshot_attempts  = F("sureshot_attempts")  + agg["sureshot_q"]
        summary.applied_attempts   = F("applied_attempts")   + agg["applied_q"]
        summary.guesswork_attempts = F("guesswork_attempts") + agg["guesswork_q"]
        summary.blind_attempts     = F("blind_attempts")     + agg["blind_q"]

        summary.sureshot_wrong  = F("sureshot_wrong")  + agg["sureshot_wrong"]
        summary.applied_wrong   = F("applied_wrong")   + agg["applied_wrong"]
        summary.guesswork_wrong = F("guesswork_wrong") + agg["guesswork_wrong"]
        summary.blind_wrong     = F("blind_wrong")     + agg["blind_wrong"]

        summary.net_marks       = F("net_marks") + net_marks
        summary.save()


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

    if qlog.user_answered:                                 # -------- NEW -----
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
# ── SUMMARY PAGE (simple) ─────────────────────────────────────
@login_required
def practice_summary(request, session_id):
    session = get_object_or_404(
        PracticeSession, id=session_id, user=request.user
    )
    logs = session.questionlog_set.order_by("serial")
    return render(
        request,
        "practice/practice_summary.html",
        {"session": session, "logs": logs},
    )

@login_required
def practice_home(request):
    user = request.user

    # 1. Ongoing (pending) practice sessions
    pending_sessions = PracticeSession.objects.filter(
        user=user,
        status='pending'
    )

    # Allow new session creation only if fewer than 2 are active
    can_create = pending_sessions.count() < 2

    # 2. Previous (completed) sessions, most recent first
    previous_sessions = PracticeSession.objects.filter(
        user=user,
        status='completed'
    ).order_by('-end_time')

    # 3. All subjects for the chained form and subject-tree nav
    subjects = Subject.objects.all().order_by('name')

    # 4. All OLT types for the dropdown
    olts = OLT.objects.all().order_by('name')

    return render(request, 'practice/practice_home.html', {
        'pending_sessions':  pending_sessions,
        'can_create':        can_create,
        'previous_sessions': previous_sessions,
        'subjects':          subjects,
        'olts':              olts,
    })


@login_required
def create_practice(request):
    if request.method != "POST":
        return redirect("practice:practice_home")

    user = request.user

    # ── Guard: only allow 2 pending sessions ───────────────────
    if PracticeSession.objects.filter(user=user, status="pending").count() >= 2:
        messages.warning(request, "You already have two active practice sessions.")
        return redirect("practice:practice_home")

    # ------------------------------------------------------------------
    # 1. Grab IDs from the POST form
    # ------------------------------------------------------------------
    subject_id  = request.POST.get("subject")   or None
    section_id  = request.POST.get("section")   or None
    topic_id    = request.POST.get("topic")     or None
    subtopic_id = request.POST.get("subtopic")  or None
    olt_id      = request.POST.get("olt_type")  or None
    order_mode  = request.POST.get("order", "serial") or "serial"

    # ------------------------------------------------------------------
    # 2. If the user clicked the topic-link shortcut, derive parents
    # ------------------------------------------------------------------
    # (subject_id is empty but topic_id is provided)
    if not subject_id and topic_id:
        topic_obj   = get_object_or_404(Topic, pk=topic_id)
        section_obj = topic_obj.section
        subject_obj = section_obj.subject
        # Override IDs to keep rest of logic simple
        section_id  = section_obj.id
        subject_id  = subject_obj.id

    # ------------------------------------------------------------------
    # 3. Convert IDs to objects (safe even if None)
    # ------------------------------------------------------------------
    subject  = get_object_or_404(Subject, pk=subject_id)   if subject_id  else None
    section  = get_object_or_404(Section, pk=section_id)   if section_id  else None
    topic    = get_object_or_404(Topic,   pk=topic_id)     if topic_id    else None
    subtopic = get_object_or_404(SubTopic, pk=subtopic_id) if subtopic_id else None
    olt      = get_object_or_404(OLT, pk=olt_id)           if olt_id      else None

    # ------------------------------------------------------------------
    # 4. Create session, pull ALL questions for deepest filter
    # ------------------------------------------------------------------
    if not subject or not topic:
        messages.error(request, "Please select at least a subject and topic.")
        return redirect("practice:practice_home")
    qs = Question.objects.all()
    if subtopic:  qs = qs.filter(subtopic=subtopic)
    elif topic:   qs = qs.filter(topic=topic)
    elif section: qs = qs.filter(section=section)
    elif subject: qs = qs.filter(subject=subject)
    if olt:       qs = qs.filter(olt=olt)

    ids = list(qs.values_list("id", flat=True))
    if order_mode == "random":
        random.shuffle(ids)
    else:
        ids.sort(reverse=True)

    qs_count = len(ids)
    if qs_count < 4:
        messages.error(request, "Not enough questions available for the selected filters.")
        return redirect("practice:practice_home")
    
    session = PracticeSession.objects.create(
        user=user, subject=subject, section=section,
        topic=topic, subtopic=subtopic, status="pending",total_questions=qs_count,
    )

    

    QuestionLog.objects.bulk_create([
        QuestionLog(
            user=user, question_id=qid, practiceSession=session,
            serial=idx, attempt_type="unattempted"
        )
        for idx, qid in enumerate(ids, start=1)
    ])

    session.total_questions = len(ids)
    session.save()

    return redirect("practice:take_practice", session.id)




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
    # Fetch subject with its hierarchy
    subject = get_object_or_404(
        Subject.objects.prefetch_related(
            'sections__topics__subtopics'
        ),
        pk=subject_id
    )

    # Build a serializable structure
    sections_data = []
    for section in subject.sections.all():
        topics_data = []
        for topic in section.topics.all():
            # Lookup the user’s practice summary (if any)
            summary = topic.topicattemptsummary_set.filter(
                user=request.user, mode='practice'
            ).first()
            # Determine color
            if summary:
                acc = summary.accuracy
                if acc > 80:
                    color = 'green'
                elif acc > 50 and acc <= 80:
                    color = 'orange'
                elif acc <= 49:
                    color = 'red'
                
            else:
                color = 'grey'

            # Subtopics
            subs = [
                {'id': sub.id, 'name': sub.name}
                for sub in topic.subtopics.all()
            ]

            topics_data.append({
                'id':        topic.id,
                'name':      topic.name,
                'color':     color,
                'subtopics': subs,
            })

        sections_data.append({
            'name':   section.name,
            'topics': topics_data,
        })

    return render(request, "practice/partials/subject_tree.html", {
        'sections': sections_data,
    })

@login_required
def topic_summary(request):
    

    target_user = request.user
    user_qs_param = request.GET.get("user")
    if user_qs_param and request.user.is_staff:
        target_user = get_object_or_404(User, pk=user_qs_param)

    summaries = (
        TopicAttemptSummary.objects
        .filter(user=target_user)
        .select_related("topic__section__subject", "topic__section")
        .order_by("topic__name", "mode")
    )

    all_users = User.objects.only("id", "username").order_by("username")

    context = {
        "target_user": target_user,
        "summaries": summaries,
        "all_users": all_users,
    }
    return render(request, "practice/topic_summary.html", context)