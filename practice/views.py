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
from django.core.paginator import Paginator
from django.db.models import F, FloatField, Value, Case, When, ExpressionWrapper
from django.utils.http import urlencode




@login_required
def topic_summary(request):
    target_user = request.user
    user_qs_param = request.GET.get("user")
    if user_qs_param and request.user.is_staff:
        target_user = get_object_or_404(User, pk=user_qs_param)

    # Base queryset
    summaries = (
        TopicAttemptSummary.objects
        .filter(user=target_user)
        .select_related("topic__section__subject", "topic__section")
    )

    # ---- Filters ----
    valid_modes = {value for value, _ in TopicAttemptSummary.MODE_CHOICES}
    mode = (request.GET.get("mode") or "").strip()
    if mode and mode in valid_modes:
        summaries = summaries.filter(mode=mode)
    else:
        mode = ""  # normalize

    q = (request.GET.get("q") or "").strip()
    if q:
        summaries = summaries.filter(topic__name__icontains=q)

    # ---- Sorting ----
    # Annotate WRONG RATE so we can sort it at the DB level
    wrong_rate_expr = Case(
        When(total_attempts=0, then=Value(0.0)),
        default=ExpressionWrapper(
            100.0 * F("wrong_attempts") / F("total_attempts"),
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )
    summaries = summaries.annotate(wrong_rate_value=wrong_rate_expr)

    # Map sort keys -> ORM fields (or annotated names)
    sort_map = {
        "topic": "topic__name",
        "mode": "mode",
        "total": "total_attempts",
        "correct": "correct_attempts",
        "wrong": "wrong_attempts",
        "wrong_rate": "wrong_rate_value",   # <-- use this instead of accuracy
        "net": "net_marks",
        "ss": "sureshot_attempts",
        "ap": "applied_attempts",
        "gw": "guesswork_attempts",
        "bl": "blind_attempts",
        "ssw": "sureshot_wrong",
        "apw": "applied_wrong",
        "gww": "guesswork_wrong",
        "blw": "blind_wrong",
        "mi": "mastery_index",
    }

    sort_key = (request.GET.get("sort") or "topic").strip()
    sort_dir = (request.GET.get("dir") or "asc").strip().lower()
    orm_field = sort_map.get(sort_key, "topic__name")

    if sort_dir == "desc":
        summaries = summaries.order_by(f"-{orm_field}", "topic__name", "mode")
    else:
        summaries = summaries.order_by(orm_field, "topic__name", "mode")

    # Keep other params when toggling sort
    base_params = request.GET.copy()
    base_params.pop("sort", None)
    base_params.pop("dir", None)
    base_qs = urlencode(base_params, doseq=True)

    all_users = User.objects.only("id", "username").order_by("username")

    context = {
        "target_user": target_user,
        "summaries": summaries,
        "all_users": all_users,
        "mode_choices": TopicAttemptSummary.MODE_CHOICES,
        "current_mode": mode,
        "q": q,
        "active_sort": sort_key,
        "active_dir": sort_dir,
        "base_qs": base_qs,
    }
    return render(request, "practice/topic_summary.html", context)




def start_capsule_subject(request):
    return render(
        request,
        "practice/practice_home.html", )

@login_required
def history_page(request):
    sessions = PracticeSession.objects.filter(user=request.user).order_by("-end_time")
    page_obj  = Paginator(sessions, 5).get_page(request.GET.get("page", 1))
    return render(request,
                  "practice/partials/history_rows.html",
                  {"page_obj": page_obj})


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
        
        sureshot_wrong  = Count("id", filter=Q(attempt_type="sureshot", attempt_result="wrong")),
        applied_wrong   = Count("id", filter=Q(attempt_type="applied",  attempt_result="wrong")),
        guesswork_wrong = Count("id", filter=Q(attempt_type="guesswork",attempt_result="wrong")),
        
    )

    wrong_q      = agg["answered_q"] - agg["correct_q"]
    unattempted  = agg["total_q"]    - agg["answered_q"]
    print("finalise tak to aya")

    # Simple net-mark rule (+2 / −0.66) – tweak if you use a different formula
    net_marks = (agg["correct_q"] * 2) - (wrong_q * 0.66)

    attempt_count = agg["answered_q"]

    with transaction.atomic():                            # -------- NEW --------
        # ── update PracticeSession ────────────────────────────────────────────
        session.total_questions   = agg["total_q"]
        session.correct_answers   = agg["correct_q"]
        session.unattempted       = unattempted
        session.total_score       = net_marks

        session.sureshot_attempts = agg["sureshot_q"]
        session.applied_attempts  = agg["applied_q"]
        session.guesswork_attempts= agg["guesswork_q"]
        

        session.sureshot_wrong    = agg["sureshot_wrong"]
        session.applied_wrong     = agg["applied_wrong"]
        session.guesswork_wrong   = agg["guesswork_wrong"]
      

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
        

        summary.sureshot_wrong  = F("sureshot_wrong")  + agg["sureshot_wrong"]
        summary.applied_wrong   = F("applied_wrong")   + agg["applied_wrong"]
        summary.guesswork_wrong = F("guesswork_wrong") + agg["guesswork_wrong"]
        

        summary.net_marks       = F("net_marks") + net_marks
        summary.save()
        session.user.profile.register_attempt(increment=attempt_count)


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
    print("yaha to araha hai ")
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
            print("Khatam")
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
    """
    If session is PENDING:
      - and all questions are answered -> finalize, then show summary
      - and some question(s) are pending -> redirect to dashboard
    If session is COMPLETE: render summary
    """
    session = get_object_or_404(PracticeSession, id=session_id, user=request.user)

    # Adjust these to your actual status values/enums if different
    PENDING  = "pending"
    COMPLETE = "completed"

    # First unanswered question (None means all answered)
    next_log = (
        session.questionlog_set
        .filter(user_answered__isnull=True)
        .order_by("serial")
        .first()
    )
    print(session.status)
    if session.status == PENDING:
        
        if next_log is None:
            # All questions answered → finalize once, then show summary
            _finalise_session_and_update_summary(session)
            session.refresh_from_db()
            logs = session.questionlog_set.order_by("serial")
            return render(
                request,
                "practice/practice_summary.html",
                {"session": session, "logs": logs},
            )
        else:
            # Still has pending questions → send user back to dashboard
            return redirect("dashboard")  # ← change to your actual dashboard URL name
    elif session.status == COMPLETE:
        # Already complete → show summary
        logs = session.questionlog_set.order_by("serial")
        return render(
            request,
            "practice/practice_summary.html",
            {"session": session, "logs": logs},
        )

    # Fallback: if status is something else, be conservative and send to dashboard
    return redirect("dashboard")

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
    for the sidebar / modal.  Each topic is colour-coded by accuracy and,
    when the user has attempted it in practice mode, displays its wrong-rate
    inside parentheses.

      • green   : accuracy  > 80 %
      • orange  : accuracy  50 – 80 %
      • red     : accuracy  < 50 %
      • grey    : no attempts yet

    Template:  practice/partials/subject_tree.html
    """

    subject = get_object_or_404(
        Subject.objects.prefetch_related('sections__topics__subtopics'),
        pk=subject_id
    )

    sections_data = []
    for section in subject.sections.all():
        topics_data = []
        for topic in section.topics.all():

            # ── fetch practice summary for the current user ──────────
            summary: TopicAttemptSummary | None = (
                topic.topicattemptsummary_set
                     .filter(user=request.user, mode='practice')
                     .first()
            )

            if summary and summary.total_attempts:
                # percentage values already provided by model helpers
                accuracy   = summary.accuracy          # 0-100 %
                wrong_pct  = round(summary.wrong_rate, 1)  # keep one decimal

                if accuracy > 80:
                    color = 'green'
                elif 50 <= accuracy <= 80:
                    color = 'orange'
                else:
                    color = 'red'
            else:
                # no attempts yet
                wrong_pct = None
                color = 'grey'

            topics_data.append({
                'id':        topic.id,
                'name':      topic.name,
                'color':     color,
                'wrong_pct': wrong_pct,      # None when grey
                'subtopics': [
                    {'id': sub.id, 'name': sub.name}
                    for sub in topic.subtopics.all()
                ],
            })

        sections_data.append({
            'name':   section.name,
            'topics': topics_data,
        })

    return render(
        request,
        "practice/partials/subject_tree.html",
        {'sections': sections_data},
    )

@login_required
def topic_modal(request, topic_id):
    user = request.user
    topic = get_object_or_404(Topic, pk=topic_id)
    topic_summary=TopicAttemptSummary.objects.filter(topic_id=topic_id, mode="practice",user=user).first()

    # Build the same practice URL you currently use on topic.name
    practice_url = reverse("practice:create_practice") + f"?topic={topic.id}"

    # Example extra info; adapt to your schema
    # If you store questions elsewhere, adjust the count query accordingly
    num_questions = getattr(topic, "num_questions", None)
    if num_questions is None:
        # e.g., if relation name is `questions`
        try:
            num_questions = topic.questions.count()
        except Exception:
            num_questions = None

    return render(
        request,
        "practice/partials/topic_modal.html",
        {
            "topic": topic,
            "topic_summary":topic_summary,
            "practice_url": practice_url,
            "num_questions": num_questions,
        },
    )

def modal_empty(request):
    # Returning empty clears the modal when swapped into #modal-root
    return HttpResponse("")


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

# @login_required
# def topic_summary(request):
    

#     target_user = request.user
#     user_qs_param = request.GET.get("user")
#     if user_qs_param and request.user.is_staff:
#         target_user = get_object_or_404(User, pk=user_qs_param)

#     summaries = (
#         TopicAttemptSummary.objects
#         .filter(user=target_user)
#         .select_related("topic__section__subject", "topic__section")
#         .order_by("topic__name", "mode")
#     )

#     all_users = User.objects.only("id", "username").order_by("username")

#     context = {
#         "target_user": target_user,
#         "summaries": summaries,
#         "all_users": all_users,
#     }
#     return render(request, "practice/topic_summary.html", context)