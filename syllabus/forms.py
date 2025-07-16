from django import forms
from .models import Exam, Subject, Topic, SubTopic, MicroTopic, Ques
from ckeditor.widgets import CKEditorWidget



class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}

class SubTopicForm(forms.ModelForm):
    class Meta:
        model = SubTopic
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}

class MicroTopicForm(forms.ModelForm):
    class Meta:
        model = MicroTopic
        fields = ['name']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}

class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'name': 'Exam Name',
            'description': 'Description (optional)',
        }


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }



class QuesEditForm(forms.ModelForm):
    class Meta:
        model = Ques
        exclude = ['q_no']
        widgets = {
            'q_statement': CKEditorWidget(),
            'explanation': CKEditorWidget(),
        }


class QuesForm(forms.ModelForm):
    class Meta:
        model = Ques
        fields = [
            'q_statement', 'a', 'b', 'c', 'd', 'correct_option', 
            'exam', 'year', 'olt',
        ]
        widgets = {
            'q_statement': CKEditorWidget(),            
            'a': forms.Textarea(attrs={'rows':2}),
            'b': forms.Textarea(attrs={'rows':2}),
            'c': forms.Textarea(attrs={'rows':2}),
            'd': forms.Textarea(attrs={'rows':2}),
        }