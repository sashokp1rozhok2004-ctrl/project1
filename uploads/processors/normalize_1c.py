from pathlib import Path
import re
import pandas as pd
import numpy as np


# Префиксы строк документов и системных групп 1С, которые игнорируются при сборе клиентов
DOCUMENT_PREFIXES = (
    "реализация",
    "заказ клиента",
    "акт выполненных работ",
    "возврат",
    "корректировка",
    "субаренда по договору",
    "отчет комиссионера",
    "<продажи без заказа>",
)


def extract_period_month(raw_df: pd.DataFrame) -> str:
    """
    Автоматически находит период в шапке отчета 1С и возвращает месяц в формате YYYY-MM.
    """
    rows_to_check = min(12, len(raw_df))
    
    for row_idx in range(rows_to_check):
        row_str = " ".join(raw_df.iloc[row_idx].dropna().astype(str))
        
        # Поиск даты формата DD.MM.YYYY (например, 01.04.2026 или 01.05.2026)
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", row_str)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month}"

    raise ValueError("Не удалось определить период/месяц из шапки отчета 1С.")


def clean_article(value) -> str:
    """
    Очищает артикул товара от лишних пробелов и текстовых хвостов '.0'.
    """
    if pd.isna(value):
        return None
    
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
        
    return text if text else None


def clean_client_name(client_str: str) -> str:
    """
    Очищает наименование клиента (оставляет только основное название до слэша).
    """
    if pd.isna(client_str):
        return ""
    
    text = str(client_str).strip()
    if " / " in text:
        text = text.split(" / ")[0].strip()
        
    return text


def find_table_header(raw_df: pd.DataFrame) -> int:
    """
    Ищет номер строки заголовков таблицы (содержащей Номенклатура, Артикул, Количество).
    """
    for row_idx in range(min(15, len(raw_df))):
        row_values = [str(val).lower() for val in raw_df.iloc[row_idx].values]
        has_item = any("номенклатура" in v for v in row_values)
        has_article = any("артикул" in v for v in row_values)
        has_qty = any("количество" in v for v in row_values)
        
        if has_item and has_article and has_qty:
            return row_idx
            
    raise ValueError("Не найдена строка заголовков таблицы 1С.")


def parse_1c_erp_report(file_path: Path) -> pd.DataFrame:
    """
    Преобразует иерархический отчет 1С ERP в плоскую фактовую таблицу с точной фильтрацией папок 1С:
    [client, product_article, product_name, month, actual_qty_1c, actual_revenue_1c]
    """
    file_path = Path(file_path)
    
    if file_path.suffix.lower() in [".csv", ".txt"]:
        raw_df = pd.read_csv(file_path, header=None, low_memory=False)
    else:
        raw_df = pd.read_excel(file_path, header=None)

    # 1. Извлечение периода (месяца YYYY-MM)
    target_month = extract_period_month(raw_df)
    
    # 2. Поиск заголовка
    header_row = find_table_header(raw_df)
    header_values = [str(val).lower().strip() for val in raw_df.iloc[header_row].values]
    
    col_item_idx = 0
    col_article_idx = 4
    col_qty_idx = 6
    col_revenue_idx = 7

    for idx, h_val in enumerate(header_values):
        if "номенклатура" in h_val:
            col_item_idx = idx
        elif "артикул" in h_val:
            col_article_idx = idx
        elif "количество" in h_val:
            col_qty_idx = idx
        elif "выручка" in h_val:
            col_revenue_idx = idx

    # 3. Обход строк отчета
    data_rows = []
    
    current_article = None
    current_product_name = None
    product_total_qty = 0.0
    product_total_revenue = 0.0
    collected_qty = 0.0
    collected_revenue = 0.0

    for row_idx in range(header_row + 1, len(raw_df)):
        row = raw_df.iloc[row_idx]
        
        col_item_val = str(row[col_item_idx]).strip() if pd.notna(row[col_item_idx]) else ""
        col_article_val = clean_article(row[col_article_idx]) if col_article_idx < len(row) else None
        
        qty_val = pd.to_numeric(row[col_qty_idx], errors="coerce") if col_qty_idx < len(row) else 0.0
        revenue_val = pd.to_numeric(row[col_revenue_idx], errors="coerce") if col_revenue_idx < len(row) else 0.0

        qty_val = 0.0 if pd.isna(qty_val) else float(qty_val)
        revenue_val = 0.0 if pd.isna(revenue_val) else float(revenue_val)

        # 1. Если в строке есть АРТИКУЛ -> Это уровень ТОВАРА
        if col_article_val:
            current_article = col_article_val
            current_product_name = col_item_val
            product_total_qty = qty_val
            product_total_revenue = revenue_val
            collected_qty = 0.0
            collected_revenue = 0.0
            continue

        # 2. Если мы внутри товара (current_article зафиксирован)
        if current_article and col_item_val:
            col_item_lower = col_item_val.lower()

            # Пропускаем детализацию документов
            if any(col_item_lower.startswith(prefix) for prefix in DOCUMENT_PREFIXES):
                continue

            # Пропускаем служебные шапки компании
            if col_item_val in ["ВБК РУС", "Итого", "Параметры:"]:
                continue

            # Проверяем, не собрали ли мы уже 100% продаж по текущему товару
            all_revenue_collected = (product_total_revenue > 0) and (collected_revenue >= product_total_revenue - 0.01)
            all_qty_collected = (product_total_qty > 0) and (collected_qty >= product_total_qty - 0.001)

            if all_revenue_collected or all_qty_collected:
                # Все клиенты для этого товара уже найдены! Дальнейшие строки без артикула — это папки 1С -> пропускаем!
                current_article = None
                current_product_name = None
                continue

            # Игнорируем папки 1С с техническими префиксами кодов (например "12739074_...") или хранение
            if "ответственное хранение" in col_item_lower or re.match(r"^\d{6,}_", col_item_val):
                continue

            # Записываем ЧИСТОГО клиента
            if qty_val > 0 or revenue_val > 0:
                client_clean = clean_client_name(col_item_val)
                
                data_rows.append({
                    "client": client_clean,
                    "product_article": current_article,
                    "product_name": current_product_name,
                    "month": target_month,
                    "actual_qty_1c": qty_val,
                    "actual_revenue_1c": revenue_val,
                })

                collected_qty += qty_val
                collected_revenue += revenue_val

                # Если после этого клиента собрали 100%, закрываем контекст товара
                if (product_total_revenue > 0 and collected_revenue >= product_total_revenue - 0.01) or \
                   (product_total_qty > 0 and collected_qty >= product_total_qty - 0.001):
                    current_article = None
                    current_product_name = None

    result_df = pd.DataFrame(data_rows)
    
    if result_df.empty:
        raise ValueError("Не удалось извлечь ни одной строки продаж из отчета 1С.")

    # 4. Агрегация по (Клиент + Артикул + Товар + Месяц)
    aggregated_df = (
        result_df.groupby(["client", "product_article", "product_name", "month"], as_index=False)
        .agg({"actual_qty_1c": "sum", "actual_revenue_1c": "sum"})
    )

    return aggregated_df