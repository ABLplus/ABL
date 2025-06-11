from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from .forms import *
from tests.models import Test
from django.db.models import Max



def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'user/home.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            mobile_number = form.cleaned_data.get('mobile_number')
            if mobile_number:
                try:
                    user.profile.mobile_number = mobile_number
                    user.profile.save()
                except Profile.DoesNotExist:
                    pass  # No profile exists, just ignore
            auth_login(request, user)
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'user/register.html', {'form': form})

def login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'user/login.html', {'form': form})

def logout(request):
    if request.method == 'POST':
        auth_logout(request)
        return redirect('home')


@login_required
def dashboard(request):
    years = list(range(2000, 2025))

    user_tests = Test.objects.filter(user=request.user)
    pending_tests = user_tests.filter(status='pending')
    completed_tests = user_tests.filter(status='completed')

    pending_tests_with_next_serial = []

    for test in pending_tests:
        highest_attempt = test.questionlog_set.filter(user_answered__isnull=False).aggregate(Max('serial'))['serial__max']
        if highest_attempt:
            if highest_attempt == test.total_questions:
                next_serial = highest_attempt
            else:
                next_serial = highest_attempt + 1
        else:
            next_serial = 1  # No attempt yet
        pending_tests_with_next_serial.append((test, next_serial))

    # Prepare completed_tests_with_metrics
    completed_tests_with_metrics = []
    for test in completed_tests:
        sureshot_wrongrate = "-"
        if test.sureshot_attempts:
            sureshot_wrongrate = round((test.sureshot_wrong / test.sureshot_attempts) * 100, 1)

        applied_wrongrate = "-"
        if test.applied_attempts:
            applied_wrongrate = round((test.applied_wrong / test.applied_attempts) * 100, 1)

        guesswork_wrongrate = "-"
        if test.guesswork_attempts:
            guesswork_wrongrate = round((test.guesswork_wrong / test.guesswork_attempts) * 100, 1)

        blind_attempt_impact = "-"
        if test.blind_attempts:
            blind_attempt_impact = (test.blind_attempts - test.blind_wrong) * 2 - (test.blind_wrong * 2/3)
            blind_attempt_impact = round(blind_attempt_impact, 1)

        completed_tests_with_metrics.append({
            'test': test,
            'sureshot_wrongrate': sureshot_wrongrate,
            'applied_wrongrate': applied_wrongrate,
            'guesswork_wrongrate': guesswork_wrongrate,
            'blind_attempt_impact': blind_attempt_impact,
        })

    context = {
        'years': years,
        'pending_tests_with_next_serial': pending_tests_with_next_serial,
        'completed_tests_with_metrics': completed_tests_with_metrics,
    }
    return render(request, 'user/dashboard.html', context)


@login_required
def delete_test(request, test_id):
    test = get_object_or_404(Test, id=test_id, user=request.user)

    if test.status == 'pending':  # Only allow deleting pending tests
        test.delete()

    return redirect('dashboard')


@login_required
def profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user.profile)

    return render(request, 'user/profile.html', {'form': form})
