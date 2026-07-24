from django.conf import settings
from django.db import models


class UploadedFile(models.Model):
    MANAGERS = [
        ("khusnutdinov", "Хуснутдинов А."),
        ("redko", "Редько В."),
        ("izmailov", "Измайлов М."),
        ("mustafin", "Мустафин Р."),
        ("polyakov", "Поляков А."),
        ("prasolov_soloviev", "Прасолов и Соловьёв"),
        ("fomichev", "Фомичев В."),
        ("khoroshevsky", "Хорошевский А."),
        ("tsarev", "Царёв М."),
        ("ushakov", "Ушаков А."),
    ]

    FILE_TYPES = [
        ("manager_forecast", "План и прогноз менеджера"),
        ("actual_sales", "Фактические продажи"),
        ("other", "Другой файл"),
    ]

    file = models.FileField(
        upload_to="uploads/%Y/%m/%d/"
    )

    original_name = models.CharField(
        max_length=255
    )

    file_type = models.CharField(
        max_length=30,
        choices=FILE_TYPES,
        default="manager_forecast",
    )

    manager = models.CharField(
        max_length=40,
        choices=MANAGERS,
        blank=True,
        null=True,
    )

    forecast_date = models.DateField(
        verbose_name="Дата прогноза",
        blank=True,
        null=True,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_files",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    size_bytes = models.PositiveBigIntegerField(
        default=0
    )
    VALIDATION_STATUSES = [
        ("not_checked", "Не проверен"),
        ("valid", "Проверен"),
        ("warning", "Есть предупреждения"),
        ("error", "Ошибка"),
    ]

    validation_status = models.CharField(
        max_length=20,
        choices=VALIDATION_STATUSES,
        default="not_checked",
    )

    sheet_count = models.PositiveIntegerField(
        default=0,
    )

    row_count = models.PositiveIntegerField(
        default=0,
    )

    column_count = models.PositiveIntegerField(
        default=0,
    )

    validation_message = models.TextField(
        blank=True,
        default="",
    )

    validated_at = models.DateTimeField(
        blank=True,
        null=True,
    )
    def __str__(self):
        return self.original_name