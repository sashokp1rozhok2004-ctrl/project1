from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UploadFileForm
from .models import UploadedFile

from .validators import validate_uploaded_file

from pathlib import Path

from django.http import FileResponse, Http404

def is_analyst(user):
    return (
        user.is_superuser
        or user.groups.filter(name="Analyst").exists()
    )


def build_manager_statuses():
    files = UploadedFile.objects.order_by("-uploaded_at")

    latest_manager_files = {}

    for file_item in files:
        if (
            file_item.file_type == "manager_forecast"
            and file_item.manager
            and file_item.manager not in latest_manager_files
        ):
            latest_manager_files[file_item.manager] = file_item

    return [
        {
            "code": manager_code,
            "name": manager_name,
            "file": latest_manager_files.get(manager_code),
        }
        for manager_code, manager_name in UploadedFile.MANAGERS
    ]


@login_required
def upload_files(request):
    if not is_analyst(request.user):
        return render(
            request,
            "uploads/access_denied.html",
            status=403,
        )

    if request.method == "POST":
        form = UploadFileForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            uploaded_file = form.save(commit=False)
            source_file = request.FILES["file"]

            uploaded_file.original_name = source_file.name
            uploaded_file.size_bytes = source_file.size
            uploaded_file.uploaded_by = request.user
            uploaded_file.save()
            validate_uploaded_file(uploaded_file)

            return redirect("uploads:upload_files")
    else:
        form = UploadFileForm()

    files = UploadedFile.objects.order_by("-uploaded_at")

    actual_sales_file = (
        UploadedFile.objects
        .filter(file_type="actual_sales")
        .order_by("-uploaded_at")
        .first()
    )

    other_company_files = (
        UploadedFile.objects
        .filter(file_type="other")
        .order_by("-uploaded_at")
    )

    return render(
        request,
        "uploads/upload_files.html",
        {
            "form": form,
            "files": files,
            "manager_statuses": build_manager_statuses(),
            "actual_sales_file": actual_sales_file,
            "other_company_files": other_company_files,
        },
    )   


@login_required
def edit_file(request, file_id):
    if not is_analyst(request.user):
        return render(
            request,
            "uploads/access_denied.html",
            status=403,
        )

    uploaded_file = get_object_or_404(
        UploadedFile,
        id=file_id,
    )

    old_file_path = uploaded_file.file.name

    if request.method == "POST":
        form = UploadFileForm(
            request.POST,
            request.FILES,
            instance=uploaded_file,
        )

        if form.is_valid():
            updated_file = form.save(commit=False)

            if "file" in request.FILES:
                new_file = request.FILES["file"]

                updated_file.original_name = new_file.name
                updated_file.size_bytes = new_file.size

                if old_file_path:
                    uploaded_file.file.storage.delete(old_file_path)

            updated_file.save()
            validate_uploaded_file(updated_file)

            return redirect("uploads:upload_files")
    else:
        form = UploadFileForm(instance=uploaded_file)

    return render(
        request,
        "uploads/edit_file.html",
        {
            "form": form,
            "uploaded_file": uploaded_file,
        },
    )


@login_required
def delete_file(request, file_id):
    if not is_analyst(request.user):
        return render(
            request,
            "uploads/access_denied.html",
            status=403,
        )

    uploaded_file = get_object_or_404(
        UploadedFile,
        id=file_id,
    )

    if request.method == "POST":
        stored_file = uploaded_file.file

        uploaded_file.delete()

        if stored_file:
            stored_file.delete(save=False)

        return redirect("uploads:upload_files")

    return render(
        request,
        "uploads/delete_file.html",
        {
            "uploaded_file": uploaded_file,
        },
    )

@login_required
def download_file(request, file_id):
    if not is_analyst(request.user):
        return render(
            request,
            "uploads/access_denied.html",
            status=403,
        )

    uploaded_file = get_object_or_404(
        UploadedFile,
        id=file_id,
    )

    try:
        file_handle = uploaded_file.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Файл не найден на диске.")

    download_name = (
        uploaded_file.original_name
        or Path(uploaded_file.file.name).name
    )

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=download_name,
    )


@login_required
def processing_readiness(request):
    if not is_analyst(request.user):
        return render(
            request,
            "uploads/access_denied.html",
            status=403,
        )

    manager_statuses = build_manager_statuses()

    loaded_managers = [
        manager
        for manager in manager_statuses
        if manager["file"] is not None
    ]

    missing_managers = [
        manager
        for manager in manager_statuses
        if manager["file"] is None
    ]

    problem_managers = [
        manager
        for manager in manager_statuses
        if (
            manager["file"] is not None
            and manager["file"].validation_status != "valid"
        )
    ]

    actual_sales_file = (
        UploadedFile.objects
        .filter(file_type="actual_sales")
        .order_by("-uploaded_at")
        .first()
    )

    manager_files_ready = (
        len(loaded_managers) == len(UploadedFile.MANAGERS)
    )

    manager_files_valid = (
        manager_files_ready
        and not problem_managers
    )

    actual_sales_ready = (
        actual_sales_file is not None
        and actual_sales_file.validation_status == "valid"
    )

    ready_for_processing = (
        manager_files_valid
        and actual_sales_ready
    )

    progress_percent = int(
        len(loaded_managers)
        / len(UploadedFile.MANAGERS)
        * 100
    )

    return render(
        request,
        "uploads/processing_readiness.html",
        {
            "manager_statuses": manager_statuses,
            "loaded_managers": loaded_managers,
            "missing_managers": missing_managers,
            "problem_managers": problem_managers,
            "actual_sales_file": actual_sales_file,
            "manager_files_ready": manager_files_ready,
            "manager_files_valid": manager_files_valid,
            "actual_sales_ready": actual_sales_ready,
            "ready_for_processing": ready_for_processing,
            "progress_percent": progress_percent,
        },
    )