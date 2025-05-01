# user/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile

class CustomUserCreationForm(UserCreationForm):
    mobile_number = forms.CharField(
        max_length=15, 
        required=False, 
        help_text="Optional. Enter your mobile number."
    )

    class Meta:
        model = User
        fields = ('username', 'mobile_number', 'password1', 'password2')



class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('mobile_number',)
        widgets = {
            'mobile_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your mobile number'}),
        }