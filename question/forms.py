from django import forms
from .models import Question
from ckeditor.widgets import CKEditorWidget

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = [
            'source_type', 'year', 'subject_name', 'topic', 'subtopic',
            'question_html', 'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'difficulty_level', 'nature', 'explanation_html'
        ]
        widgets = {
            'question_html': CKEditorWidget(),
            'explanation_html': CKEditorWidget(),
        }
