from pathlib import Path
import pandas as pd
import numpy as np

# Словарь для перевода номеров месяцев в русские названия
MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# Ключевые слова для автоматического определения клиентов Ушакова из выгрузки 1С
USHAKOV_CLIENTS_KEYWORDS = [
    "норма", "тдспа", "мегаавтозапчасть", "набиева", "бав-движение", 
    "стфк камаз", "комтранс", "евротехпарт", "автофургон", "ато трейд", 
    "автотрак", "автозапчасть", "бренор", "тракдрайв", "мир грузовиков", 
    "нитавто", "тонарь", "платформа", "майер групп", "траксторбел"
]


def find_column(df: pd.DataFrame, candidates: list) -> str:
    """Возвращает имя первой найденной колонки из списка кандидатов."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def is_ushakov_client(client_str: str) -> bool:
    """Проверяет, относится ли клиент из 1С к пулу клиентов Ушакова."""
    if pd.isna(client_str):
        return False
    c_lower = str(client_str).lower()
    return any(kw in c_lower for kw in USHAKOV_CLIENTS_KEYWORDS)


def clean_str(series: pd.Series) -> pd.Series:
    """Очищает текстовые ключи для корректного совпадения при объединении."""
    return series.fillna("").astype(str).str.strip().str.lower().str.replace("ё", "е")


def extract_period_key(df: pd.DataFrame) -> pd.Series:
    """Формирует ключ периода YYYY-MM независимо от формата колонок в файле."""
    month_col = find_column(df, ["month", "Месяц_строка"])
    if month_col:
        return df[month_col].astype(str)

    year_col = find_column(df, ["Год", "year"])
    m_num_col = find_column(df, ["Номер месяца", "month_num"])

    if year_col and m_num_col:
        years = pd.to_numeric(df[year_col], errors="coerce").fillna(2026).astype(int)
        months = pd.to_numeric(df[m_num_col], errors="coerce").fillna(1).astype(int)
        return years.astype(str) + "-" + months.map(lambda x: f"{x:02d}")

    return pd.Series(["2026-01"] * len(df), index=df.index)


def merge_plans_and_1c(plans_df: pd.DataFrame, actuals_1c_df: pd.DataFrame) -> pd.DataFrame:
    """
    Формирует итоговую фактовую витрину в ТОЧНОМ СООТВЕТСТВИИ со структурой Loginom / DataLens.
    Поддерживает как русские, так и английские названия заголовков.
    """
    plans = plans_df.copy()
    actuals = actuals_1c_df.copy()

    # Определение колонок клиента и артикула
    client_col_plan = find_column(plans, ["client", "Клиент", "Контрагент", "Ключ клиента"])
    article_col_plan = find_column(plans, ["product_article", "Артикул", "Код товара"])

    client_col_1c = find_column(actuals, ["client", "Клиент", "Контрагент", "Ключ клиента"])
    article_col_1c = find_column(actuals, ["product_article", "Артикул", "Код товара"])

    manager_col_plan = find_column(plans, ["manager", "Менеджер"])

    # 1. Приведение клиентов Ушакова к единой плановой группе
    if manager_col_plan and client_col_plan:
        mask_ushakov_plan = plans[manager_col_plan].astype(str).str.contains("Ушаков", case=False, na=False)
        plans.loc[mask_ushakov_plan, client_col_plan] = "Клиенты Ушакова (Пул)"

    if client_col_1c:
        mask_ushakov_1c = actuals[client_col_1c].apply(is_ushakov_client)
        actuals.loc[mask_ushakov_1c, client_col_1c] = "Клиенты Ушакова (Пул)"

    # 2. Служебные ключи объединения
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

    # 4. Восстановление разрезов (Dimensions)
    c_plan = find_column(merged, [f"{client_col_plan}_plan", client_col_plan, "Клиент_plan", "Клиент"])
    c_1c = find_column(merged, [f"{client_col_1c}_1c", client_col_1c, "Клиент_1c", "Клиент"])
    merged["Клиент"] = merged[c_plan].fillna(merged[c_1c]) if c_plan and c_1c else (merged[c_plan] if c_plan else merged[c_1c])

    a_plan = find_column(merged, [f"{article_col_plan}_plan", article_col_plan, "Артикул_plan", "Артикул"])
    a_1c = find_column(merged, [f"{article_col_1c}_1c", article_col_1c, "Артикул_1c", "Артикул"])
    merged["Артикул"] = merged[a_plan].fillna(merged[a_1c]) if a_plan and a_1c else (merged[a_plan] if a_plan else merged[a_1c])

    p_name_col = find_column(merged, ["product_name_plan", "product_name", "Наименование_plan", "Наименование", "Наименование_1c"])
    merged["Наименование"] = merged[p_name_col].fillna("") if p_name_col else ""

    # Менеджер
    m_col = find_column(merged, ["manager_plan", "manager", "Менеджер_plan", "Менеджер"])
    merged["Менеджер"] = merged[m_col].fillna("Неизвестен / Из 1С") if m_col else "Неизвестен / Из 1С"
    merged.loc[merged["Клиент"] == "Клиенты Ушакова (Пул)", "Менеджер"] = "Ушаков Алексей"

    # Поставщик
    s_col = find_column(merged, ["supplier_plan", "supplier", "Поставщик_plan", "Поставщик"])
    merged["Поставщик"] = merged[s_col].fillna("ВБК Рус") if s_col else "ВБК Рус"

    # Даты и месяц
    month_str = merged["_key_month"]
    month_dt = pd.to_datetime(month_str, format="%Y-%m", errors="coerce")
    
    merged["Год"] = month_dt.dt.year.fillna(2026).astype(int)
    merged["Номер месяца"] = month_dt.dt.month.fillna(1).astype(int)
    merged["Месяц"] = merged["Номер месяца"].map(MONTH_NAMES_RU)

    # 5. Определение цены товара в юанях из планов
    price_col = find_column(merged, [
        "Цена, юань, без НДС 1 п/г 2026", "price_cny_plan", "price_cny", 
        "price", "unit_price", "price_1"
    ])
    if price_col:
        merged["Цена, юань, без НДС 1 п/г 2026"] = pd.to_numeric(merged[price_col], errors="coerce").fillna(0.0)
    else:
        merged["Цена, юань, без НДС 1 п/г 2026"] = 0.0

    # 6. КОЛИЧЕСТВЕННЫЕ ПОКАЗАТЕЛИ (шт)
    aop_col = find_column(merged, ["AOP, шт", "aop_plan", "aop"])
    forecast_col = find_column(merged, ["Прогноз, шт", "forecast_plan", "forecast"])
    
    merged["AOP, шт"] = pd.to_numeric(merged[aop_col], errors="coerce").fillna(0.0) if aop_col else 0.0
    merged["Прогноз, шт"] = pd.to_numeric(merged[forecast_col], errors="coerce").fillna(0.0) if forecast_col else 0.0
    
    # ФАКТ ШТ: берем свежий из 1С, при отсутствии — не затираем имеющийся
    fact_qty_1c_col = find_column(merged, ["actual_qty_1c", "Факт, шт_1c"])
    fact_qty_plan_col = find_column(merged, ["Факт, шт_plan", "Факт, шт", "actual_plan", "actual"])
    
    fact_qty_1c = pd.to_numeric(merged[fact_qty_1c_col], errors="coerce") if fact_qty_1c_col else pd.Series(np.nan, index=merged.index)
    fact_qty_plan = pd.to_numeric(merged[fact_qty_plan_col], errors="coerce") if fact_qty_plan_col else pd.Series(np.nan, index=merged.index)
    
    merged["Факт, шт"] = fact_qty_1c.combine_first(fact_qty_plan).fillna(0.0)

    # 7. ДЕНЕЖНЫЕ ПОКАЗАТЕЛИ (CNY / Юани)
    merged["AOP, CNY"] = (merged["AOP, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)
    merged["Прогноз, CNY"] = (merged["Прогноз, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)

    # ФАКТ ЮАНИ: Заносим напрямую из 1С без пересчета
    fact_rev_1c_col = find_column(merged, ["actual_revenue_1c", "Факт, CNY_1c", "Факт, юань, без НДС_1c"])
    fact_rev_plan_col = find_column(merged, ["Факт, юань, без НДС_plan", "Факт, юань, без НДС", "Факт, CNY_plan", "Факт, CNY"])
    
    fact_rev_1c = pd.to_numeric(merged[fact_rev_1c_col], errors="coerce") if fact_rev_1c_col else pd.Series(np.nan, index=merged.index)
    fact_rev_plan = pd.to_numeric(merged[fact_rev_plan_col], errors="coerce") if fact_rev_plan_col else pd.Series(np.nan, index=merged.index)
    
    fact_cny_final = fact_rev_1c.combine_first(fact_rev_plan).fillna(0.0).round(2)
    
    merged["Факт, CNY"] = fact_cny_final
    merged["Факт, юань, без НДС"] = fact_cny_final

    # 8. СТРОГИЙ ПОРЯДОК КОЛОНОК
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