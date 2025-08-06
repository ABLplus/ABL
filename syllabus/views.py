
from django.shortcuts import render, redirect, get_object_or_404
from .models import Exam,Topic, Subject, SubTopic, MicroTopic, Ques, Section
from .forms import ExamForm, SubjectForm, TopicForm, MicroTopicForm, SubTopicForm, QuesEditForm, QuesForm
from django.urls import reverse
from utils.llm_module import call_gpt_explanation
from collections import defaultdict
from question.models import Question    
from django.http import HttpResponseBadRequest
from django.db.models import Count, Q
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def ques_summary_view(request):
    """
    Subject → Section → Topic summary with clickable
    Unchecked / Review / Checked counts.
    """

    # ------------------------------------------------ 1. aggregated counts
    agg = (
        Ques.objects
            .values('subject_id', 'section_id', 'topic_id')
            .annotate(
                unchecked=Count('id', filter=Q(is_check=False, for_review=False)),
                review   =Count('id', filter=Q(for_review=True,  is_check=False)),
                checked  =Count('id', filter=Q(is_check=True)),
            )
            .order_by('subject_id', 'section_id', 'topic_id')
    )

    # ------------------------------------------------ 2. lookup maps
    UNASSIGNED = 'Unassigned'
    subj_name = {s.id: s.name for s in Subject.objects.all()}
    sect_name = {s.id: s.name for s in Section.objects.all()}
    topic_name= {t.id: t.name for t in Topic.objects.all()}

    # ------------------------------------------------ 3. build nested tree  subj ▸ sect ▸ [topics]
    tree = defaultdict(lambda: defaultdict(list))
    for row in agg:
        subj_id   = row['subject_id']
        section_id= row['section_id']
        topic_id  = row['topic_id']

        tree[subj_id][section_id].append({
            'id':        topic_id,
            'name':      topic_name.get(topic_id, UNASSIGNED),
            'unchecked': row['unchecked'],
            'review':    row['review'],
            'checked':   row['checked'],
        })

    # ------------------------------------------------ 4. compute totals & flatten to list
    subjects = []
    for subj_id, sec_dict in tree.items():
        subject_tot_un = subject_tot_rev = subject_tot_chk = 0
        section_list = []

        for sect_id, topics in sec_dict.items():
            sec_un  = sum(t['unchecked'] for t in topics)
            sec_rev = sum(t['review']    for t in topics)
            sec_chk = sum(t['checked']   for t in topics)

            subject_tot_un  += sec_un
            subject_tot_rev += sec_rev
            subject_tot_chk += sec_chk

            section_list.append({
                'id':              sect_id,
                'name':            sect_name.get(sect_id, UNASSIGNED),
                'total_unchecked': sec_un,
                'total_review':    sec_rev,
                'total_checked':   sec_chk,
                'topics':          topics,
            })

        subjects.append({
            'id':              subj_id,
            'name':            subj_name.get(subj_id, UNASSIGNED),
            'total_unchecked': subject_tot_un,
            'total_review':    subject_tot_rev,
            'total_checked':   subject_tot_chk,
            'sections':        section_list,
        })

    # sort subjects alphabetically for easy scan
    subjects.sort(key=lambda x: x['name'])

    return render(request, 'syllabus/ques_summary.html', { 'subjects': subjects })
@staff_member_required
def section_topic_subtopic_view(request):
    selected_subject_id = request.GET.get('subject')
    subjects = Subject.objects.all()
    structured_data = []

    selected_subject = None
    if selected_subject_id:
        try:
            selected_subject = Subject.objects.get(id=selected_subject_id)
        except Subject.DoesNotExist:
            selected_subject = None

    if selected_subject:
        # Preload related objects
        sections = Section.objects.filter(subject=selected_subject).prefetch_related('topics__subtopics')
        # Count questions by section/topic/subtopic
        ques_queryset = Question.objects.filter(subject=selected_subject).values(
            'section_id', 'topic_id', 'subtopic_id'
        )

        # Prepare counts
        section_counts = defaultdict(int)
        topic_counts = defaultdict(int)
        subtopic_counts = defaultdict(int)

        for q in ques_queryset:
            section_counts[q['section_id']] += 1
            topic_counts[q['topic_id']] += 1
            subtopic_counts[q['subtopic_id']] += 1

        # Build hierarchical structure
        for section in sections:
            topics_data = []
            for topic in section.topics.all():
                subtopics_data = []
                for sub in topic.subtopics.all():
                    subtopics_data.append({
                        'name': sub.name,
                        'count': subtopic_counts.get(sub.id, 0)
                    })
                topics_data.append({
                    'name': topic.name,
                    'count': topic_counts.get(topic.id, 0),
                    'subtopics': subtopics_data
                })
            structured_data.append({
                'name': section.name,
                'count': section_counts.get(section.id, 0),
                'topics': topics_data
            })

    return render(request, 'syllabus/section_topic_subtopics.html', {
        'sections': structured_data,
        'subjects': subjects,
        'selected_subject_id': int(selected_subject_id) if selected_subject_id else None
    })
@staff_member_required
def generate_explanation(request, pk):
    ques = get_object_or_404(Ques, id=pk)

    if request.method == 'POST':
        data = {
            "q_markdown": ques.q_markdown,
            "a": ques.a,
            "b": ques.b,
            "c": ques.c,
            "d": ques.d,
            "correct_option": ques.correct_option,
        }

        generated_exp = call_gpt_explanation(data)

        ques.exp_generated = generated_exp
        ques.save()

    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or f"/ques/edit/?index=0")
@staff_member_required   
def ques_list(request):
    questions = Ques.objects.all().order_by('id')
    return render(request, 'syllabus/ques_list.html', {'questions': questions})
@staff_member_required
def edit_ques(request, pk):
    ques = get_object_or_404(Ques, pk=pk)
    total_questions = Ques.objects.count()

    if request.method == 'POST':
        form = QuesEditForm(request.POST, instance=ques)
        if form.is_valid():
            form.save()
            return redirect('edit_ques', pk=ques.pk)
    else:
        form = QuesEditForm(instance=ques)

    return render(request, 'syllabus/edit_ques.html', {
        'form': form,
        'ques': ques,
        'total_questions': total_questions,
        'right_column_fields': ["explanation", "exam", "year", 'exp_generated', 'section_name', 'topic_name', 'subtopic_name',
          ],
    })

@staff_member_required
def subject_detail_view(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    topics = subject.topics.prefetch_related('subtopics__microtopics')

    if request.method == 'POST':
        if 'add_topic' in request.POST:
            form = TopicForm(request.POST)
            if form.is_valid():
                topic = form.save(commit=False)
                topic.subject = subject
                topic.save()
                return redirect('subject_detail', subject_id=subject.id)

        elif 'add_subtopic' in request.POST:
            topic_id = request.POST.get('topic_id')
            topic = get_object_or_404(Topic, id=topic_id)
            form = SubTopicForm(request.POST)
            if form.is_valid():
                subtopic = form.save(commit=False)
                subtopic.topic = topic
                subtopic.save()
                return redirect('subject_detail', subject_id=subject.id)

        elif 'add_microtopic' in request.POST:
            subtopic_id = request.POST.get('subtopic_id')
            subtopic = get_object_or_404(SubTopic, id=subtopic_id)
            form = MicroTopicForm(request.POST)
            if form.is_valid():
                microtopic = form.save(commit=False)
                microtopic.subtopic = subtopic
                microtopic.save()
                return redirect('subject_detail', subject_id=subject.id)

        elif 'delete_topic' in request.POST:
            Topic.objects.filter(id=request.POST.get('topic_id')).delete()
            return redirect('subject_detail', subject_id=subject.id)

        elif 'delete_subtopic' in request.POST:
            SubTopic.objects.filter(id=request.POST.get('subtopic_id')).delete()
            return redirect('subject_detail', subject_id=subject.id)

        elif 'delete_microtopic' in request.POST:
            MicroTopic.objects.filter(id=request.POST.get('microtopic_id')).delete()
            return redirect('subject_detail', subject_id=subject.id)
        
        elif 'edit_topic' in request.POST:
            topic_id = request.POST.get('topic_id')
            topic = get_object_or_404(Topic, id=topic_id)
            form = TopicForm(request.POST, instance=topic)
            if form.is_valid():
                form.save()
            return redirect('subject_detail', subject_id=subject.id)

        elif 'edit_subtopic' in request.POST:
            subtopic_id = request.POST.get('subtopic_id')
            subtopic = get_object_or_404(SubTopic, id=subtopic_id)
            form = SubTopicForm(request.POST, instance=subtopic)
            if form.is_valid():
                form.save()
            return redirect('subject_detail', subject_id=subject.id)

        elif 'edit_microtopic' in request.POST:
            microtopic_id = request.POST.get('microtopic_id')
            microtopic = get_object_or_404(MicroTopic, id=microtopic_id)
            form = MicroTopicForm(request.POST, instance=microtopic)
            if form.is_valid():
                form.save()
            return redirect('subject_detail', subject_id=subject.id)
    
    return render(request, 'syllabus/subject_detail.html', {
        'subject': subject,
        'topics': topics,
        'topic_form': TopicForm(),
        'subtopic_form': SubTopicForm(),
        'microtopic_form': MicroTopicForm()
    })
@staff_member_required
def exams_view(request):
    exams = Exam.objects.all()
    form = ExamForm()

    if request.method == 'POST':
        if 'save_exam' in request.POST:
            exam_id = request.POST.get('exam_id')
            instance = Exam.objects.get(id=exam_id) if exam_id else None
            form = ExamForm(request.POST, instance=instance)
            if form.is_valid():
                form.save()
                return redirect('exams_view')
        elif 'delete_exam' in request.POST:
            exam_id = request.POST.get('exam_id')
            Exam.objects.filter(id=exam_id).delete()
            return redirect('exams_view')

    context = {
        'exams': exams,
        'form': form
    }
    return render(request, 'syllabus/exams.html', context)
@staff_member_required
def exam_detail_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    subjects = exam.subjects.all()
    subject_form = SubjectForm()

    if request.method == 'POST':
        if 'save_subject' in request.POST:
            subject_id = request.POST.get('subject_id')
            instance = Subject.objects.get(id=subject_id) if subject_id else None
            subject_form = SubjectForm(request.POST, instance=instance)
            if subject_form.is_valid():
                new_subject = subject_form.save(commit=False)
                new_subject.exam = exam
                new_subject.save()
                return redirect('exam_detail', exam_id=exam.id)
        
        elif 'delete_subject' in request.POST:
            subject_id = request.POST.get('subject_id')
            Subject.objects.filter(id=subject_id, exam=exam).delete()
            return redirect('exam_detail', exam_id=exam.id)

    context = {
        'exam': exam,
        'subjects': subjects,
        'subject_form': subject_form
    }
    return render(request, 'syllabus/exam_detail.html', context)







def safe_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None

@staff_member_required
def ques_edit_view(request):
    # ---------------------------------------------------- 1. dropdown data
    if request.method == 'POST':
        print("POST received")
    exams    = Ques.objects.values_list('exam', flat=True).distinct()
    subjects = Subject.objects.all()
    years    = Ques.objects.values_list('year', flat=True).distinct()
    units    = Ques.objects.values_list('unit', flat=True).distinct()

    # ---------------------------------------------------- 2. selected filter values
    f_sid  = request.GET.get('subject_id')
    sec_id = request.GET.get('section_id')
    t_id   = request.GET.get('topic_id')
    st_id  = request.GET.get('subtopic_id')

    sections           = Section.objects.filter(subject_id=f_sid)     if f_sid else []
    filter_topics      = Topic.objects.filter(section_id=sec_id)      if sec_id and sec_id != 'none' else []
    filter_subtopics   = SubTopic.objects.filter(topic_id=t_id)       if t_id   and t_id   != 'none' else []
    filter_microtopics = MicroTopic.objects.filter(subtopic_id=st_id) if st_id and st_id != 'none' else []

    # ---------------------------------------------------- 3. build queryset filters
    filters = {}
    def add_filter(qd, key, cast_int=False):
        val = qd.get(key)
        if val == 'not_assigned':
            filters[f'{key}__isnull'] = True
        elif val not in (None, '', 'none', 'None'):
            filters[key] = safe_int(val) if cast_int else val

    add_filter(request.GET, 'exam')
    add_filter(request.GET, 'year',        cast_int=True)
    add_filter(request.GET, 'unit',        cast_int=True)
    add_filter(request.GET, 'subject_id',  cast_int=True)
    add_filter(request.GET, 'section_id',  cast_int=True)
    add_filter(request.GET, 'topic_id',    cast_int=True)
    add_filter(request.GET, 'subtopic_id', cast_int=True)

    # tri-state for_review / is_check
    fr_flag = request.GET.get('for_review')              # 'true' | 'false' | '' / None
    if fr_flag == 'true':
        filters['for_review'] = True
        filters['is_check']   = False
    elif fr_flag == 'false':
        filters['is_check'] = True
    else:
        # default view → only unchecked questions
        filters['is_check']   = False
        filters['for_review'] = False

    # ---------------------------------------------------- 4. queryset + initial question
    qs    = Ques.objects.filter(**filters).order_by('id')
    total = qs.count()

    try:
        index = int(request.GET.get('index', 0))
    except (TypeError, ValueError):
        index = 0
    if index >= total:
        index = 0

    question = qs[index] if total else None

    # ---------------------------------------------------- 5. handle POST (save / mark)
    if request.method == 'POST':
        qid = request.POST.get('question_id')
        if qid:
            question = get_object_or_404(Ques, pk=int(qid))

        form = QuesForm(request.POST, instance=question)

        if form.is_valid():
            action = request.POST.get('action')
            obj    = form.save(commit=False)

            # update flags
            if action == 'checked':
                obj.is_check, obj.for_review = True, False
            elif action == 'for_review':
                obj.is_check, obj.for_review = False, True

            # save FK selections from inline dropdowns
            obj.subject_id   = request.POST.get('subject_id')   or None
            obj.section_id   = request.POST.get('section_id')   or None
            obj.topic_id     = request.POST.get('topic_id')     or None
            obj.subtopic_id  = request.POST.get('subtopic_id')  or None

            obj.save()

            # advance index within the still-filtered list
            new_ids = list(
                Ques.objects.filter(**filters)
                            .order_by('id')
                            .values_list('id', flat=True)
            )
            try:
                cur_idx = new_ids.index(obj.id)
            except ValueError:
                cur_idx = -1
            next_idx = (cur_idx + 1) % len(new_ids) if new_ids else 0

            params = request.GET.copy()
            params['index'] = next_idx
            return redirect(f"{reverse('ques_edit')}?{params.urlencode()}")
    else:
        form = QuesForm(instance=question)

    # ---------------------------------------------------- 6. status / progress counts
    base_filters = {k: v for k, v in filters.items() if k not in ('is_check', 'for_review')}
    base_qs        = Ques.objects.filter(**base_filters)
    unchecked_cnt  = base_qs.filter(is_check=False, for_review=False).count()
    review_cnt     = base_qs.filter(for_review=True, is_check=False).count()
    checked_cnt    = base_qs.filter(is_check=True).count()
    total_ques_cnt = unchecked_cnt + review_cnt + checked_cnt
    progress_pct   = (checked_cnt * 100 // total) if total else 0

    # nav params without index
    get_params = request.GET.copy()
    get_params.pop('index', None)

    # ---------------------------------------------------- 7. render
    return render(
        request,
        'syllabus/q_edit.html',
        {
            'form':               form,
            'question':           question,
            'exams':              exams,
            'subjects':           subjects,
            'years':              years,
            'units':              units,
            'sections':           sections,
            'filter_topics':      filter_topics,
            'filter_subtopics':   filter_subtopics,
            'filter_microtopics': filter_microtopics,

            'index':         index,
            'total':         total,

            'unchecked':     unchecked_cnt,
            'review':        review_cnt,
            'checked':       checked_cnt,
            'total_ques':    total_ques_cnt,
            'width_percent': progress_pct,

            'get_params':    get_params.urlencode(),
        }
    )


# HTMX Dropdown Views

def get_section_dropdown(request):
    mode = request.GET.get('mode', 'filter')  # 'filter' or 'edit'
    subject_id = request.GET.get('subject_id') or request.GET.get('subject')
    selected   = request.GET.get('section_id') or request.GET.get('section')

    sections = Section.objects.filter(subject_id=subject_id) if subject_id and subject_id != 'none' else []

    tpl = 'syllabus/partials/section_edit_dropdown.html' \
          if mode == 'edit' else \
          'syllabus/partials/section_dropdown_filter.html'

    return render(request, tpl, {
        'sections':    sections,
        'selected_id': selected,
    })



def get_topic_dropdown(request):
    mode       = request.GET.get('mode', 'filter')              # 'filter' (default) or 'edit'
    section_id = request.GET.get('section_id') or request.GET.get('section')
    selected   = request.GET.get('topic_id')   or request.GET.get('topic')

    topics = Topic.objects.filter(section_id=section_id) if section_id and section_id != 'none' else []

    tpl = (
        'syllabus/partials/topic_edit_dropdown.html'
        if mode == 'edit'
        else 'syllabus/partials/topic_dropdown_filter.html'
    )

    return render(request, tpl, {
        'topics'     : topics,
        'selected_id': selected,
    })




def get_subtopic_dropdown(request):
    mode     = request.GET.get('mode', 'filter')
    topic_id = request.GET.get('topic_id') or request.GET.get('topic')
    selected = request.GET.get('subtopic_id') or request.GET.get('subtopic')

    subtopics = SubTopic.objects.filter(topic_id=topic_id) if topic_id and topic_id != 'none' else []

    tpl = (
        'syllabus/partials/subtopic_edit_dropdown.html'
        if mode == 'edit'
        else 'syllabus/partials/subtopic_dropdown_filter.html'
    )

    return render(request, tpl, {
        'subtopics'  : subtopics,
        'selected_id': selected,
    })