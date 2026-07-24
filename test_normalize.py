from pathlib import Path
import pandas as pd

from uploads.processors.normalize_manager import (
    KNOWN_MANAGERS,
    get_available_months,
    prepare_wide_table,
    transform_months,
)

# Папка с исходными файлами
MEDIA_UPLOADS_DIR = Path("media/uploads")

# Отдельная папка для результатов (будет создана автоматически)
OUTPUT_DIR = Path("results")


def find_all_manager_files(base_dir: Path) -> list:
    """
    Сканирует media/uploads/ и корневую директорию, 
    находит все оригинальные файлы планов менеджеров.
    Игнорирует папку результатов results/.
    """
    search_dirs = [base_dir, Path(".")]
    all_files = []

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue

        for ext in ["*.xlsx", "*.xlsm", "*.xls"]:
            for f_path in s_dir.rglob(ext):
                # Игнорируем файлы из папки результатов
                if OUTPUT_DIR.name in f_path.parts:
                    continue

                name_clean = f_path.name.lower().replace("ё", "е")

                # Исключаем выгрузки результатов и временные файлы Excel
                if (
                    "result" in name_clean
                    or name_clean.startswith("~$")
                    or "wide_" in name_clean
                    or "normalized_" in name_clean
                ):
                    continue

                # Файл подходит, если совпадает фамилия менеджера ИЛИ есть ключевые слова планов
                has_manager = any(m in name_clean for m in KNOWN_MANAGERS)
                has_keywords = "план" in name_clean or "инд" in name_clean

                if has_manager or has_keywords:
                    all_files.append(f_path)

    # Группируем по имени файла и оставляем самый свежий вариант
    unique_files_by_name = {}
    for f in all_files:
        fname = f.name
        if (
            fname not in unique_files_by_name
            or f.stat().st_mtime > unique_files_by_name[fname].stat().st_mtime
        ):
            unique_files_by_name[fname] = f

    result_files = list(unique_files_by_name.values())
    result_files.sort(key=lambda f: f.name)

    return result_files


def process_single_file(target_file: Path) -> pd.DataFrame:
    """
    Полная нормализация одного файла и сохранение в папку results/.
    """
    print("\n" + "=" * 60)
    print(f"📄 ОБРАБОТКА ФАЙЛА: [{target_file.name}]")
    print(f"📁 Полный путь: {target_file.resolve()}")
    print("=" * 60)

    # 1. Сборка широкой таблицы
    wide_df = prepare_wide_table(target_file)
    print(f"Размер широкой таблицы: {wide_df.shape}")

    # Извлечение имён менеджеров, содержащихся внутри файла
    managers_in_file = (
        wide_df["manager"].dropna().astype(str).unique().tolist()
    )
    print(f"Менеджер(ы) в файле: {', '.join(managers_in_file)}")

    # 2. Трансформация UNPIVOT в длинный формат
    final_df = transform_months(wide_df)
    print(f"Размер итоговой таблицы (строк, столбцов): {final_df.shape}")

    # Сохранение промежуточного файла в отдельную папку results/
    clean_stem = target_file.stem.replace(" ", "_")
    output_path = OUTPUT_DIR / f"normalized_{clean_stem}_result.xlsx"
    final_df.to_excel(output_path, index=False)
    print(f"✅ Результат сохранен в: {output_path.resolve()}")

    return final_df


def main():
    print("=" * 60)
    print("🚀 АВТОМАТИЧЕСКИЙ СКАНЕР И НОРМАЛИЗАТОР ФАЙЛОВ МЕНЕДЖЕРОВ")
    print("=" * 60)

    # Автоматически создаем папку для результатов, если её ещё нет
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Папка для сохранения результатов: {OUTPUT_DIR.resolve()}\n")

    found_files = find_all_manager_files(MEDIA_UPLOADS_DIR)

    if not found_files:
        print("❌ Не найдено ни одного файла планов продаж!")
        return

    print(f"📌 Найдено файлов для обработки: {len(found_files)}")
    for idx, f in enumerate(found_files, 1):
        print(f"  {idx}. {f.name}")

    normalized_dfs = []
    failed_files = []

    for file_path in found_files:
        try:
            df_norm = process_single_file(file_path)
            normalized_dfs.append(df_norm)
        except Exception as e:
            print(f"❌ Ошибка при обработке файла {file_path.name}: {e}")
            failed_files.append((file_path.name, str(e)))

    # Объединение всех обработанных файлов в общую фактовую витрину
    if normalized_dfs:
        print("\n" + "=" * 60)
        print("📦 СБОРКА ЕДИННОЙ ВИКРИНЫ ДАННЫХ ПО ВСЕМ МЕНЕДЖЕРАМ")
        print("=" * 60)

        all_managers_df = pd.concat(normalized_dfs, ignore_index=True)
        
        # Сохранение итоговой общей витрины в папку results/
        all_output_path = OUTPUT_DIR / "normalized_all_managers_result.xlsx"
        all_managers_df.to_excel(all_output_path, index=False)

        print(f"Успешно обработано файлов: {len(normalized_dfs)}")
        print(f"Общий размер витрины данных: {all_managers_df.shape} (строк x колонок)")
        print(f"Уникальных менеджеров в итоговом массиве: {all_managers_df['Менеджер'].nunique()}")
        mgr_col = 'Менеджер' if 'Менеджер' in all_managers_df.columns else 'manager'
        if mgr_col in all_managers_df.columns:
            print(f"Список всех менеджеров: {list(all_managers_df[mgr_col].dropna().unique())}")
        print(f"✅ Общий итоговый файл сохранен: {all_output_path.resolve()}")

    if failed_files:
        print("\n⚠️ Файлы, вызвавшие ошибки при обработке:")
        for fname, err in failed_files:
            print(f"  - {fname}: {err}")


if __name__ == "__main__":
    main()