from pathlib import Path
import pandas as pd
import numpy as np

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


def find_column(df: pd.DataFrame, candidates: list) -> str:
    for col in candidates:
        if col in df.columns:
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
    plans = plans_df.copy()
    actuals = actuals_1c_df.copy()

    # Определение колонок
    client_col_plan = find_column(plans, ["client", "Клиент", "Контрагент", "Ключ клиента"])
    article_col_plan = find_column(plans, ["product_article", "Артикул", "Код товара"])

    client_col_1c = find_column(actuals, ["client", "Клиент", "Контрагент", "Ключ клиента"])
    article_col_1c = find_column(actuals, ["product_article", "Артикул", "Код товара"])

    manager_col_plan = find_column(plans, ["manager", "Менеджер"])

    # 1. Приведение клиентов Ушакова к единому пулу
    if manager_col_plan and client_col_plan:
        mask_ushakov_plan = plans[manager_col_plan].astype(str).str.contains("Ушаков", case=False, na=False)
        plans.loc[mask_ushakov_plan, client_col_plan] = "Клиенты Ушакова (Пул)"

    if client_col_1c:
        mask_ushakov_1c = actuals[client_col_1c].apply(is_ushakov_client)
        actuals.loc[mask_ushakov_1c, client_col_1c] = "Клиенты Ушакова (Пул)"

    # 2. Формирование строгих ключей связывания
    plans["_key_client"] = clean_str(plans[client_col_plan]) if client_col_plan else ""
    plans["_key_article"] = clean_str(plans[article_col_plan]) if article_col_plan else ""
    plans["_key_month"] = clean_str(extract_period_key(plans))

    actuals["_key_client"] = clean_str(actuals[client_col_1c]) if client_col_1c else ""
    actuals["_key_article"] = clean_str(actuals[article_col_1c]) if article_col_1c else ""
    actuals["_key_month"] = clean_str(extract_period_key(actuals))

    # Удаляем «пустые мусорные ключи», предотвращая декартово перемножение N x M
    plans = plans[(plans["_key_client"] != "") | (plans["_key_article"] != "")].copy()
    actuals = actuals[(actuals["_key_client"] != "") | (actuals["_key_article"] != "")].copy()

    join_keys = ["_key_client", "_key_article", "_key_month"]

    # 3. ПРЕДВАРИТЕЛЬНАЯ АГРЕГАЦИЯ (Убирает дублирование объемов AOP!)
    price_col_plan = find_column(plans, ["Цена, юань, без НДС 1 п/г 2026", "Цена, юань, без НДС", "price_cny"])
    aop_col_plan = find_column(plans, ["AOP, шт", "aop_plan", "aop"])
    fc_col_plan = find_column(plans, ["Прогноз, шт", "forecast_plan", "forecast"])

    plans_agg = plans.groupby(join_keys, as_index=False).agg({
        client_col_plan: "first" if client_col_plan else lambda x: "",
        article_col_plan: "first" if article_col_plan else lambda x: "",
        manager_col_plan: "first" if manager_col_plan else lambda x: "Неизвестен",
        find_column(plans, ["supplier", "Поставщик"]): "first",
        find_column(plans, ["product_name", "Наименование"]): "first",
        price_col_plan: "mean" if price_col_plan else lambda x: 0.0,
        aop_col_plan: "sum" if aop_col_plan else lambda x: 0.0,
        fc_col_plan: "sum" if fc_col_plan else lambda x: 0.0,
    })

    qty_1c_col = find_column(actuals, ["actual_qty_1c", "Факт, шт_1c", "Факт, шт", "Количество"])
    rev_1c_col = find_column(actuals, ["actual_revenue_1c", "Факт, CNY_1c", "Выручка", "Сумма"])

    actuals_agg = actuals.groupby(join_keys, as_index=False).agg({
        client_col_1c: "first" if client_col_1c else lambda x: "",
        article_col_1c: "first" if article_col_1c else lambda x: "",
        qty_1c_col: "sum" if qty_1c_col else lambda x: 0.0,
        rev_1c_col: "sum" if rev_1c_col else lambda x: 0.0,
    })

    # 4. FULL OUTER JOIN сжатых таблиц
    merged = pd.merge(
        plans_agg,
        actuals_agg,
        on=join_keys,
        how="outer",
        suffixes=("_plan", "_1c")
    )

    # 5. Восстановление колонок
    c_plan = find_column(merged, [f"{client_col_plan}_plan", client_col_plan])
    c_1c = find_column(merged, [f"{client_col_1c}_1c", client_col_1c])
    merged["Клиент"] = merged[c_plan].fillna(merged[c_1c]) if c_plan and c_1c else (merged[c_plan] if c_plan else merged[c_1c])

    a_plan = find_column(merged, [f"{article_col_plan}_plan", article_col_plan])
    a_1c = find_column(merged, [f"{article_col_1c}_1c", article_col_1c])
    merged["Артикул"] = merged[a_plan].fillna(merged[a_1c]) if a_plan and a_1c else (merged[a_plan] if a_plan else merged[a_1c])

    p_name_col = find_column(merged, ["product_name", "Наименование"])
    merged["Наименование"] = merged[p_name_col].fillna("") if p_name_col else ""

    m_col = find_column(merged, [f"{manager_col_plan}_plan", manager_col_plan])
    merged["Менеджер"] = merged[m_col].fillna("Неизвестен / Из 1С") if m_col else "Неизвестен / Из 1С"
    merged.loc[merged["Клиент"] == "Клиенты Ушакова (Пул)", "Менеджер"] = "Ушаков Алексей"

    s_col = find_column(merged, ["supplier", "Поставщик"])
    merged["Поставщик"] = merged[s_col].fillna("ВБК Рус") if s_col else "ВБК Рус"

    # Даты и месяц
    month_str = merged["_key_month"]
    month_dt = pd.to_datetime(month_str, format="%Y-%m", errors="coerce")
    
    merged["Год"] = month_dt.dt.year.fillna(2026).astype(int)
    merged["Номер месяца"] = month_dt.dt.month.fillna(1).astype(int)
    merged["Месяц"] = merged["Номер месяца"].map(MONTH_NAMES_RU)

    # Цена
    p_col_res = find_column(merged, [price_col_plan, f"{price_col_plan}_plan"]) if price_col_plan else None
    merged["Цена, юань, без НДС 1 п/г 2026"] = pd.to_numeric(merged[p_col_res], errors="coerce").fillna(0.0) if p_col_res else 0.0

    # Количества
    a_col_res = find_column(merged, [aop_col_plan, f"{aop_col_plan}_plan"]) if aop_col_plan else None
    f_col_res = find_column(merged, [fc_col_plan, f"{fc_col_plan}_plan"]) if fc_col_plan else None
    q_col_res = find_column(merged, [qty_1c_col, f"{qty_1c_col}_1c"]) if qty_1c_col else None

    merged["AOP, шт"] = pd.to_numeric(merged[a_col_res], errors="coerce").fillna(0.0) if a_col_res else 0.0
    merged["Прогноз, шт"] = pd.to_numeric(merged[f_col_res], errors="coerce").fillna(0.0) if f_col_res else 0.0
    merged["Факт, шт"] = pd.to_numeric(merged[q_col_res], errors="coerce").fillna(0.0) if q_col_res else 0.0

    # Выручка
    r_col_res = find_column(merged, [rev_1c_col, f"{rev_1c_col}_1c"]) if rev_1c_col else None
    merged["AOP, CNY"] = (merged["AOP, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)
    merged["Прогноз, CNY"] = (merged["Прогноз, шт"] * merged["Цена, юань, без НДС 1 п/г 2026"]).round(2)
    
    fact_cny = pd.to_numeric(merged[r_col_res], errors="coerce").fillna(0.0).round(2) if r_col_res else 0.0
    merged["Факт, CNY"] = fact_cny
    merged["Факт, юань, без НДС"] = fact_cny

    final_columns = [
        "AOP, CNY", "Прогноз, CNY", "Факт, CNY", "Факт, юань, без НДС",
        "AOP, шт", "Прогноз, шт", "Факт, шт", "Цена, юань, без НДС 1 п/г 2026",
        "Год", "Артикул", "Месяц", "Номер месяца", "Клиент", "Менеджер", "Поставщик", "Наименование"
    ]

    return merged[final_columns]