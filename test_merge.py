from pathlib import Path
import pandas as pd
import numpy as np

OUTPUT_DIR = Path("results")

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

USHAKOV_CLIENTS_KEYWORDS = [
    "норма", "тдспа", "мегаавтозапчасть", "набиева", "бав-движение", 
    "стфк камаз", "комтранс", "евротехпарт", "автофургон", "ато трейд", 
    "автотрак", "автозапчасть", "бренор", "тракдрайв", "мир грузовиков", 
    "нитавто", "тонарь", "платформа", "майер групп", "траксторбел"
]


def find_price_column(df: pd.DataFrame) -> str:
    """Ищет ИСКЛЮЧИТЕЛЬНО колонку цены за единицу, исключая суммарные выручки."""
    for col in df.columns:
        col_str = str(col).lower()
        # Исключаем суммарные показатели
        if any(bad in col_str for bad in ["aop", "прогноз", "факт", "cny", "юань", "выручка", "сумма"]):
            continue
        if any(kw in col_str for kw in ["цена", "price", "unit_price"]):
            return col
    
    # Если строгой цены нет, ищем 'цена' с 'юань', но без AOP/Факт
    for col in df.columns:
        col_str = str(col).lower()
        if "цена" in col_str and not any(bad in col_str for bad in ["aop", "прогноз", "факт"]):
            return col
            
    return None


def find_column_by_keywords(df: pd.DataFrame, keywords: list) -> str:
    """Поиск колонки по ключевым словам."""
    for col in df.columns:
        col_lower = str(col).lower()
        if any(kw in col_lower for kw in keywords):
            return col
    return None


def is_ushakov_client(client_str: str) -> bool:
    if pd.isna(client_str):
        return False
    c_lower = str(client_str).lower()
    return any(kw in c_lower for kw in USHAKOV_CLIENTS_KEYWORDS)


def clean_str(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.lower().str.replace("ё", "е")


def extract_period_key(df: pd.DataFrame) -> pd.Series:
    month_col = find_column_by_keywords(df, ["месяц_строка", "month"])
    if month_col and not df[month_col].isna().all():
        return df[month_col].astype(str)

    year_col = find_column_by_keywords(df, ["год", "year"])
    m_num_col = find_column_by_keywords(df, ["номер месяца", "month_num"])

    if year_col and m_num_col:
        years = pd.to_numeric(df[year_col], errors="coerce").fillna(2026).astype(int)
        months = pd.to_numeric(df[m_num_col], errors="coerce").fillna(1).astype(int)
        return years.astype(str) + "-" + months.map(lambda x: f"{x:02d}")

    return pd.Series(["2026-01"] * len(df), index=df.index)


def merge_plans_and_1c(plans_df: pd.DataFrame, actuals_1c_df: pd.DataFrame) -> pd.DataFrame:
    plans = plans_df.copy()
    actuals = actuals_1c_df.copy()

    # Поиск основных полей
    client_col_plan = find_column_by_keywords(plans, ["клиент", "client", "контрагент"])
    article_col_plan = find_column_by_keywords(plans, ["артикул", "article", "код товара"])

    client_col_1c = find_column_by_keywords(actuals, ["клиент", "client", "контрагент"])
    article_col_1c = find_column_by_keywords(actuals, ["артикул", "article", "код товара"])

    manager_col_plan = find_column_by_keywords(plans, ["менеджер", "manager"])

    # 1. Группировка Ушакова
    if manager_col_plan and client_col_plan:
        mask_ushakov_plan = plans[manager_col_plan].astype(str).str.contains("Ушаков", case=False, na=False)
        plans.loc[mask_ushakov_plan, client_col_plan] = "Клиенты Ушакова (Пул)"

    if client_col_1c:
        mask_ushakov_1c = actuals[client_col_1c].apply(is_ushakov_client)
        actuals.loc[mask_ushakov_1c, client_col_1c] = "Клиенты Ушакова (Пул)"

    # 2. Ключи связывания
    plans["_key_client"] = clean_str(plans[client_col_plan]) if client_col_plan else ""
    plans["_key_article"] = clean_str(plans[article_col_plan]) if article_col_plan else ""
    plans["_key_month"] = clean_str(extract_period_key(plans))

    actuals["_key_client"] = clean_str(actuals[client_col_1c]) if client_col_1c else ""
    actuals["_key_article"] = clean_str(actuals[article_col_1c]) if article_col_1c else ""
    actuals["_key_month"] = clean_str(extract_period_key(actuals))

    join_keys = ["_key_client", "_key_article", "_key_month"]

    # 3. FULL OUTER JOIN
    merged = pd.merge(
        plans,
        actuals,
        on=join_keys,
        how="outer",
        suffixes=("_plan", "_1c")
    )

    # 4. Восстановление измерений
    c_plan = find_column_by_keywords(merged, [f"{client_col_plan}_plan", "клиент_plan", "клиент"])
    c_1c = find_column_by_keywords(merged, [f"{client_col_1c}_1c", "клиент_1c"])
    merged["Клиент"] = merged[c_plan].fillna(merged[c_1c]) if (c_plan and c_1c) else (merged[c_plan] if c_plan else merged[c_1c])

    a_plan = find_column_by_keywords(merged, [f"{article_col_plan}_plan", "артикул_plan", "артикул"])
    a_1c = find_column_by_keywords(merged, [f"{article_col_1c}_1c", "артикул_1c"])
    merged["Артикул"] = merged[a_plan].fillna(merged[a_1c]) if (a_plan and a_1c) else (merged[a_plan] if a_plan else merged[a_1c])

    p_name_col = find_column_by_keywords(merged, ["наименование", "product_name", "товар"])
    merged["Наименование"] = merged[p_name_col].fillna("") if p_name_col else ""

    # Менеджер
    m_col = find_column_by_keywords(merged, ["менеджер_plan", "manager_plan", "менеджер", "manager"])
    merged["Менеджер"] = merged[m_col].fillna("Неизвестен / Из 1С") if m_col else "Неизвестен / Из 1С"
    merged.loc[merged["Клиент"] == "Клиенты Ушакова (Пул)", "Менеджер"] = "Ушаков Алексей"

    # Поставщик
    s_col = find_column_by_keywords(merged, ["поставщик_plan", "supplier_plan", "поставщик", "supplier"])
    merged["Поставщик"] = merged[s_col].fillna("ВБК Рус") if s_col else "ВБК Рус"

    # Даты и месяц
    month_dt = pd.to_datetime(merged["_key_month"], format="%Y-%m", errors="coerce")
    merged["Год"] = month_dt.dt.year.fillna(2026).astype(int)
    merged["Номер месяца"] = month_dt.dt.month.fillna(1).astype(int)
    merged["Месяц"] = merged["Номер месяца"].map(MONTH_NAMES_RU)

    # 5. ПОИСК ЦЕНЫ (СТРОГИЙ)
    price_col = find_price_column(plans)
    if price_col:
        print(f"🎯 Найдена корректная колонка цены: '{price_col}'")
        price_series = pd.to_numeric(merged.get(f"{price_col}_plan", merged.get(price_col, 0)), errors="coerce").fillna(0.0)
    else:
        print("⚠️ Колонка индивидуальной цены за штуку не найдена в файле планов.")
        price_series = pd.Series(0.0, index=merged.index)

    merged["Цена, юань, без НДС 1 п/г 2026"] = price_series

    # 6. Количественные показатели
    aop_col = find_column_by_keywords(merged, ["aop_шт", "aop_plan", "aop"])
    forecast_col = find_column_by_keywords(merged, ["прогноз_шт", "forecast_plan", "forecast", "прогноз"])

    merged["AOP, шт"] = pd.to_numeric(merged[aop_col], errors="coerce").fillna(0.0) if aop_col else 0.0
    merged["Прогноз, шт"] = pd.to_numeric(merged[forecast_col], errors="coerce").fillna(0.0) if forecast_col else 0.0

    # ФАКТ ШТ (сохранение текущего факта)
    fact_qty_1c_col = find_column_by_keywords(merged, ["actual_qty_1c", "факт_шт_1c", "факт, шт_1c"])
    fact_qty_plan_col = find_column_by_keywords(merged, ["факт_шт_plan", "факт, шт_plan", "факт, шт", "actual_plan", "actual"])

    fact_qty_1c = pd.to_numeric(merged[fact_qty_1c_col], errors="coerce") if fact_qty_1c_col else pd.Series(np.nan, index=merged.index)
    fact_qty_plan = pd.to_numeric(merged[fact_qty_plan_col], errors="coerce") if fact_qty_plan_col else pd.Series(np.nan, index=merged.index)

    merged["Факт, шт"] = fact_qty_1c.combine_first(fact_qty_plan).fillna(0.0)

    # 7. ДЕНЕЖНЫЕ ПОКАЗАТЕЛИ (CNY)
    merged["AOP, CNY"] = (merged["AOP, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)
    merged["Прогноз, CNY"] = (merged["Прогноз, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)

    # Выручка факта напрямую из 1С без пересчета
    fact_rev_1c_col = find_column_by_keywords(merged, ["actual_revenue_1c", "факт_cny_1c", "факт, cny_1c", "факт, юань_1c"])
    fact_rev_plan_col = find_column_by_keywords(merged, ["факт_юань_plan", "факт, юань, без ндс", "факт, cny_plan", "факт, cny"])

    fact_rev_1c = pd.to_numeric(merged[fact_rev_1c_col], errors="coerce") if fact_rev_1c_col else pd.Series(np.nan, index=merged.index)
    fact_rev_plan = pd.to_numeric(merged[fact_rev_plan_col], errors="coerce") if fact_rev_plan_col else pd.Series(np.nan, index=merged.index)

    fact_cny_final = fact_rev_1c.combine_first(fact_rev_plan).fillna(0.0).round(2)

    merged["Факт, CNY"] = fact_cny_final
    merged["Факт, юань, без НДС"] = fact_cny_final

    # 8. Итоговый порядок колонок
    final_columns = [
        "AOP, CNY",
        "Прогноз, CNY",
        "Факт, CNY",
        "Факт, юань, без НДС",
        "AOP, шт",
        "Прогноз, шт",
        "Факт, шт",
        "Цена, юань, без НДС 1 п/г 2026",
        "Год",
        "Артикул",
        "Месяц",
        "Номер месяца",
        "Клиент",
        "Менеджер",
        "Поставщик",
        "Наименование"
    ]

    return merged[final_columns]


def main():
    print("=" * 60)
    print("🚀 ФОРМИРОВАНИЕ ИТОГОВОЙ ВИТРИНЫ (ЭТАЛОН LOGINOM / DATALENS)")
    print("=" * 60)

    plan_file = OUTPUT_DIR / "normalized_all_managers_result.xlsx"
    actual_files = list(OUTPUT_DIR.glob("normalized_1c_*_result.xlsx"))

    if not plan_file.exists():
        print(f"❌ Не найден файл планов: {plan_file}")
        return

    if not actual_files:
        print("❌ Не найдены обработанные файлы 1С в results/!")
        return

    plans_df = pd.read_excel(plan_file)
    actuals_1c_df = pd.concat([pd.read_excel(f) for f in actual_files], ignore_index=True)

    final_df = merge_plans_and_1c(plans_df, actuals_1c_df)

    out_path = OUTPUT_DIR / "FINAL_SALES_FACT_TABLE.xlsx"
    final_df.to_excel(out_path, index=False)

    print("\n✅ ИТОГОВЫЙ ДАТАСЕТ УСПЕШНО СФОРМИРОВАН!")
    print(f"• Итого строк: {final_df.shape[0]}")
    print(f"• Суммарный AOP: {final_df['AOP, шт'].sum():,.0f} шт. | {final_df['AOP, CNY'].sum():,.2f} ¥")
    print(f"• Суммарный Прогноз: {final_df['Прогноз, шт'].sum():,.0f} шт. | {final_df['Прогноз, CNY'].sum():,.2f} ¥")
    print(f"• Суммарный Факт 1С: {final_df['Факт, шт'].sum():,.0f} шт. | {final_df['Факт, CNY'].sum():,.2f} ¥")
    print(f"\n💾 Файл готов: {out_path.resolve()}")


if __name__ == "__main__":
    main()