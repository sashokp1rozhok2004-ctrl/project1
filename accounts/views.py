from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def home(request):
    return render(request, "accounts/home.html")


@login_required
def dashboard(request):
    # Главный администратор пока получает кабинет аналитика.
    if request.user.is_superuser:
        return render(
            request,
            "accounts/analyst_dashboard.html",
            {"role_name": "Администратор"},
        )

    if request.user.groups.filter(name="Analyst").exists():
        return render(
            request,
            "accounts/analyst_dashboard.html",
            {"role_name": "Аналитик"},
        )

    if request.user.groups.filter(name="Director").exists():
        return render(
            request,
            "accounts/director_dashboard.html",
            {"role_name": "Руководитель"},
        )

    return render(
        request,
        "accounts/no_role.html",
        status=403,
    )