import os
from pathlib import Path
import pandas as pd
from uploads.processors.normalize_manager import normalize_manager_file

MEDIA_UPLOADS_DIR = Path("media/uploads")
OUTPUT_DIR = Path("results")


def find_all_manager_files() -> list:
    """Сканирует папку загрузок и корень проекта, находит оригинальные файлы планов."""
    search_dirs = [MEDIA_UPLOADS_DIR, Path(".")]
    found_files = []

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue

        for ext in ["*.xlsx", "*.xlsm", "*.xls"]:
            for f_path in s_dir.rglob(ext):
                if OUTPUT_DIR.name in f_path.parts:
                    continue

                name_clean = f_path.name.lower().replace("ё", "е")

                if ("result" in name_clean or name_clean.startswith("~$") or 
                    "1c" in name_clean or "erp" in name_clean or "final" in name_clean):
                    continue

                if "план_продаж_инд" in name_clean or "план" in name_clean:
                    if f_path not in found_files:
                        found_files.append(f_path)

    return found_files


def main():
    print("=" * 60)
    print("🚀 ЭТАП 1: НОРМАЛИЗАЦИЯ И КОНСОЛИДАЦИЯ ПЛАНОВ МЕНЕДЖЕРОВ")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    found_files = find_all_manager_files()

    if not found_files:
        print("❌ Файлы планов менеджеров не найдены!")
        return

    print(f"📌 Найдено файлов для обработки: {len(found_files)}\n")
    normalized_dfs = []

    for idx, f_path in enumerate(found_files, 1):
        print(f"📄 [{idx}/{len(found_files)}] Обработка: {f_path.name}")
        try:
            df_norm = normalize_manager_file(f_path)
            normalized_dfs.append(df_norm)
            print(f"   ✅ Успешно! Извлечено строк: {len(df_norm):,}")
        except Exception as e:
            print(f"   ❌ Ошибка обработки {f_path.name}: {e}")

    if normalized_dfs:
        all_managers_df = pd.concat(normalized_dfs, ignore_index=True)
        out_file = OUTPUT_DIR / "normalized_all_managers_result.xlsx"
        all_managers_df.to_excel(out_file, index=False)

        print("\n" + "=" * 60)
        print("✅ КОНСОЛИДАЦИЯ ПЛАНОВ УСПЕШНО ЗАВЕРШЕНА!")
        print("=" * 60)
        print(f"• Итоговых строк планов: {len(all_managers_df):,}")
        print(f"• Суммарный AOP: {all_managers_df['AOP, шт'].sum():,.0f} шт.")
        print(f"• Суммарный Прогноз: {all_managers_df['Прогноз, шт'].sum():,.0f} шт.")
        print(f"💾 Результат сохранен в: {out_file.resolve()}")


if __name__ == "__main__":
    main()