from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import  AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, ProfileForm
from tests.models import Test
from django.db.models import Max
from django.contrib import messages
from user.utils import set_exam_session
from .models import Profile, Exam

def landing(request):
   
    return render(request, 'user/landing.html')


@login_required
def onboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        exam_id = request.POST.get("exam")
        exam_date = request.POST.get("exam_date")
        exam_year = request.POST.get("exam_year")

        if exam_id:
            profile.exam = get_object_or_404(Exam, id=exam_id)

        if exam_date:
            profile.exam_date = exam_date
            profile.exam_year = profile.exam_date.year  # keep consistent

        elif exam_year:
            profile.exam_year = exam_year

        profile.save()

        # ✅ Sync session
        set_exam_session(request, profile)

        return redirect("dashboard")

    exams = Exam.objects.all().order_by("name")
    return render(request, "user/onboard.html", {"exams": exams, "profile": profile})


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'user/landing.html')

def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # log them in immediately
            auth_login(request, user)
            return redirect("onboard")
    else:
        form = CustomUserCreationForm()

    return render(request, "user/register.html", {"form": form})


def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)

            try:
                profile = Profile.objects.select_related("exam").get(user=user)
                set_exam_session(request, profile)
            except Profile.DoesNotExist:
                request.session["exam"] = ""

            return redirect("home")

    else:
        form = AuthenticationForm()

    return render(request, "user/login.html", {"form": form})

def logout(request):
    if request.method == 'POST':
        auth_logout(request)
        return redirect('home')




@login_required
def delete_test(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)

    if test.status == 'pending':  # Only allow deleting pending tests
        test.delete()

    return redirect('dashboard')


@login_required
def profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)

            # Derive year if missing
            if profile.exam_date and not profile.exam_year:
                profile.exam_year = profile.exam_date.year

            profile.save()

            # ✅ Sync session value
            set_exam_session(request, profile)

            messages.success(request, "Profile updated successfully.")
            return redirect("home")  # Redirect to home after save

    else:
        form = ProfileForm(instance=profile)

    return render(request, "user/profile.html", {
        "form": form,
        "profile": profile,
    })

