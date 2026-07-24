from pathlib import Path

from django import forms

from .models import UploadedFile

from django.utils import timezone

class UploadFileForm(forms.ModelForm):
    class Meta:
        model = UploadedFile

        fields = [
            "file_type",
            "manager",
            "forecast_date",
            "file",
        ]

        widgets = {
            "file_type": forms.Select(),

            "manager": forms.Select(),

            "forecast_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),

            "file": forms.ClearableFileInput(
                attrs={
                    "accept": ".xlsx,.xls,.csv",
                }
            ),
        }

        labels = {
            "file_type": "Тип файла",
            "manager": "Менеджер",
            "forecast_date": "Дата прогноза",
            "file": "Файл",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["file"].required = False
        else:
            self.fields["forecast_date"].initial = timezone.localdate()

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")

        if not uploaded_file:
            if self.instance and self.instance.pk:
                return self.instance.file

            raise forms.ValidationError(
                "Выберите файл."
            )

        extension = Path(uploaded_file.name).suffix.lower()

        allowed_extensions = {
            ".xlsx",
            ".xls",
            ".csv",
        }

        if extension not in allowed_extensions:
            raise forms.ValidationError(
                "Можно загружать только файлы Excel или CSV."
            )

        max_size = 20 * 1024 * 1024

        if uploaded_file.size > max_size:
            raise forms.ValidationError(
                "Размер файла не должен превышать 20 МБ."
            )

        return uploaded_file

    def clean(self):
        cleaned_data = super().clean()

        file_type = cleaned_data.get("file_type")
        manager = cleaned_data.get("manager")
        forecast_date = cleaned_data.get("forecast_date")

        if file_type == "manager_forecast":
            if not manager:
                self.add_error(
                    "manager",
                    "Для плана и прогноза необходимо выбрать менеджера.",
                )

            if not forecast_date:
                self.add_error(
                    "forecast_date",
                    "Укажите дату прогноза.",
                )
        else:
            cleaned_data["manager"] = None
            cleaned_data["forecast_date"] = None

            if self.instance:
                self.instance.manager = None
                self.instance.forecast_date = None

        return cleaned_data
    
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["file"].required = False