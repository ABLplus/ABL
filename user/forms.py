from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile, Exam


class CustomUserCreationForm(UserCreationForm):
    mobile_number = forms.CharField(
        max_length=15,
        required=False,
        help_text="Optional. Enter your mobile number."
    )
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.all(),
        required=False,
        empty_label="Select your exam",
        initial=Exam.objects.all().first(),
        help_text="Which exam are you preparing for?"
    )
    EXAM_YEAR_CHOICES = [
        (2026, "2026"),
        (2027, "2027"),
    ]
    exam_year = forms.ChoiceField(
        choices=EXAM_YEAR_CHOICES,
        required=False,
        help_text="Which year’s exam?"
    )
    mode = forms.ChoiceField(
        choices=[("practice", "Practice"), ("test", "Test")],
        widget=forms.RadioSelect,
        initial="practice",
        help_text="Your preferred default mode."
    )

    class Meta:
        model = User
        fields = (
            "username",
            "password1",
            "password2",
            "mobile_number",
            "exam",
            "exam_year",
            "mode",
        )

    

    def save(self, commit=True):
        # 1) Create the User
        user = super().save(commit=commit)

        # 2) Pull extra form data
        mobile = self.cleaned_data.get("mobile_number")
        exam = self.cleaned_data.get("exam")
        mode = self.cleaned_data.get("mode")
        ey = self.cleaned_data.get("exam_year")
        exam_year = int(ey) if ey else None

        # 3) Map year → date
        exam_date_map = {
            2026: date(2026, 5, 25),
            2027: date(2027, 5, 31),
        }
        exam_date = exam_date_map.get(exam_year)

        if commit:
            # 4) **Update** the existing profile instead of creating a new one
            profile = user.profile     # signal already created it
            profile.mobile_number = mobile
            profile.exam           = exam
            profile.exam_year      = exam_year
            profile.exam_date      = exam_date
            profile.mode           = mode
            profile.save()

        return user


class ProfileForm(forms.ModelForm):
    EXAM_YEAR_CHOICES = [
        (2026, "2026"),
        (2027, "2027"),
    ]
    exam_year = forms.ChoiceField(
        choices=EXAM_YEAR_CHOICES,
        required=False,
        label="Exam Year"
    )

    class Meta:
        model = Profile
        fields = (
            "mobile_number",
            "exam",
            "exam_date",
            "exam_year",
            "mode",
            "streak_questions_target",
            "pledge",
            "why_exam",
        )
        widgets = {
            "mobile_number": forms.TextInput(attrs={"class": "mt-1 block w-full rounded-md"}),
            "exam": forms.Select(attrs={"class": "mt-1 block w-full rounded-md"}),
            "exam_date": forms.DateInput(attrs={"type": "date", "class": "mt-1 block w-full rounded-md"}),
            "mode": forms.RadioSelect(attrs={"class": "mt-2"}),
            "streak_questions_target": forms.NumberInput(attrs={"min": 1, "max": 1000}),
            "pledge": forms.Textarea(attrs={"rows": 4}),
            "why_exam": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "pledge": "Write a personal promise to keep yourself accountable.",
            "why_exam": "Describe your core motivation for attempting this exam.",
        }