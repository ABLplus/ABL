from django import forms
from .models import Question
from ckeditor.widgets import CKEditorWidget

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            'source_type', 'year','subject', 'subject_name', 'topic_name', 'subtopic_name',
            'question_html', 'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'difficulty_level', 'nature', 'explanation_html'
        ]
        widgets = {
            'question_html': CKEditorWidget(),
            'explanation_html': CKEditorWidget(),
        }


class QuestionRowForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            'subject',
            'section',
            'topic',
            'subtopic',
            'check_status',
        ]
        widgets = {
            'subject':   forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'section':   forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'topic':     forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'subtopic':  forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'check_status': forms.HiddenInput(),
        }