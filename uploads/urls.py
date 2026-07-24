from django.urls import path

from . import views

app_name = "uploads"

urlpatterns = [
    path("", views.upload_files, name="upload_files"),

    path(
        "<int:file_id>/edit/",
        views.edit_file,
        name="edit_file",
    ),

    path(
        "<int:file_id>/delete/",
        views.delete_file,
        name="delete_file",
    ),
    path(
        "<int:file_id>/download/",
        views.download_file,
        name="download_file",
    ),

    path(
        "readiness/",
        views.processing_readiness,
        name="processing_readiness",
    ),
]