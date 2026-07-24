import os
import re
import datetime
import pandas as pd

# 1. Словарь соответствия менеджеров
KNOWN_MANAGERS = {
    "царев": "Царев Михаил",
    "хуснутдинов": "Хуснутдинов А.",
    "редько": "Редько Вадим",
    "мустафин": "Мустафин Ринат",
    "фомичев": "Фомичев Владимир",
    "хорошевский": "Александр Хорошевский",
    "прасолов": "Прасолов Николай, Соловьёв Виктор",
    "соловьев": "Прасолов Николай, Соловьёв Виктор",
    "ушаков": "Ушаков Алексей",
    "поляков": "Поляков Андрей",
    "062026": "Измайлов",
}

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# Эталонные столбцы Loginom + сумовые денежные показатели (юани)
FINAL_COLUMNS = [
    'AOP, шт', 'Прогноз, шт', 'Факт, шт',
    'AOP, юань, без НДС', 'Прогноз, юань, без НДС', 'Факт, юань, без НДС',
    'Ключ клиента', 'Клиент', 'Менеджер', 'Год', 'Поставщик',
    'Наименование', 'Артикул', 'Цена, юань, без НДС',
    'Месяц', 'Номер месяца'
]

MONTH_COLUMN_PATTERN = re.compile(
    r"^(?P<month>\d{4}-\d{2})_(?P<metric>aop|forecast|actual|comment)$"
)


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip().lower()


def clean_client_name(client_val):
    """Очищает наименование клиента и исключает итоговые строки."""
    if pd.isna(client_val):
        return None
    
    text = str(client_val).strip()
    text_lower = text.lower()
    
    # Отсекаем итоговые/служебные строки Excel
    stop_words = ["nan", "none", "null", "0", "итого", "всего", "среднее", "баланс", "параметры"]
    if not text or any(sw in text_lower for sw in stop_words):
        return None

    if "\n" in text:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines:
            text = lines[0]

    return text if text else None


def normalize_article(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text and text.lower() not in ["nan", "none", "null"] else None


def detect_file_type(file_path):
    """Определяет имя менеджера по имени файла."""
    file_name = os.path.basename(file_path).lower().replace("ё", "е")
    detected = "Измайлов"
    for key, name in KNOWN_MANAGERS.items():
        if key in file_name:
            detected = name
            break
    return {"is_manager_plan": True, "manager_name": detected}


def parse_year_month(top_val):
    """Извлечение Года (YYYY) и Месяца (1-12)."""
    if pd.isna(top_val):
        return None, None

    try:
        if isinstance(top_val, (pd.Timestamp, datetime.datetime, datetime.date)):
            if 2000 <= top_val.year <= 2100:
                return top_val.year, top_val.month
    except Exception:
        pass

    try:
        dt = pd.to_datetime(top_val, errors="coerce")
        if pd.notna(dt) and 2000 <= dt.year <= 2100:
            return dt.year, dt.month
    except Exception:
        pass

    top_str = str(top_val).lower().strip()

    match = re.search(r"(20\d{2})[-_.\s/]+(0?[1-9]|1[0-2])\b", top_str)
    if match:
        return int(match.group(1)), int(match.group(2))

    match_rev = re.search(r"\b(0?[1-9]|1[0-2])[-_.\s/]+(20\d{2})", top_str)
    if match_rev:
        return int(match_rev.group(2)), int(match_rev.group(1))

    ru_months = {
        'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5,
        'июн': 6, 'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
    }
    year_match = re.search(r"20\d{2}", top_str)
    if year_match:
        yr = int(year_match.group(0))
        for m_prefix, m_num in ru_months.items():
            if m_prefix in top_str:
                return yr, m_num

    return None, None


def find_header_rows(raw_df):
    """Ищет строку заголовка таблицы."""
    rows_to_check = min(15, len(raw_df))
    for row_index in range(rows_to_check):
        vals = [normalize_text(v) for v in raw_df.iloc[row_index]]
        if any("подсветить" in v for v in vals):
            continue

        has_client = any(k in v for v in vals for k in ["клиент", "покупатель", "контрагент", "партнер"])
        has_article = any(k in v for v in vals for k in ["артикул", "номер изделия", "код товара"])
        has_product = any(k in v for v in vals for k in ["наименование", "номенклатура", "товар", "продукция"])

        if has_client or has_article or has_product:
            return row_index, row_index + 1

    return 2, 3


def prepare_wide_table(file_path):
    """Формирует широкую таблицу данных."""
    xls = pd.ExcelFile(file_path)
    sheet_names = [
        s for s in xls.sheet_names 
        if not any(x in s.lower() for x in ["база", "s_все", "свод", "итог", "шаблон"])
    ]
    if not sheet_names:
        sheet_names = [xls.sheet_names[0]]

    file_info = detect_file_type(file_path)
    all_sheets_dfs = []

    for sheet in sheet_names:
        raw_df = pd.read_excel(file_path, sheet_name=sheet, header=None)
        if raw_df.empty or len(raw_df) < 5:
            continue

        header_row, metric_row = find_header_rows(raw_df)

        col_map = {}
        for col_idx in range(raw_df.shape[1]):
            val = normalize_text(raw_df.iloc[header_row, col_idx])
            if any(k in val for k in ["клиент", "покупатель", "контрагент", "партнер"]):
                if "client" not in col_map:
                    col_map["client"] = col_idx
            elif any(k in val for k in ["поставщик", "завод", "производитель"]):
                if "supplier" not in col_map:
                    col_map["supplier"] = col_idx
            elif any(k in val for k in ["наименование", "номенклатура", "товар", "продукция"]):
                if "name" not in col_map:
                    col_map["name"] = col_idx
            elif any(k in val for k in ["артикул", "номер изделия", "код товара"]):
                if "article" not in col_map:
                    col_map["article"] = col_idx
            elif "цена" in val and ("юань" in val or "cny" in val):
                if "price" not in col_map:
                    col_map["price"] = col_idx

        month_cols = []
        cur_yr, cur_mo = None, None

        for col_idx in range(raw_df.shape[1]):
            top_val = raw_df.iloc[header_row, col_idx]
            yr, mo = parse_year_month(top_val)

            if (not yr or not mo) and header_row > 0:
                top_val_above = raw_df.iloc[header_row - 1, col_idx]
                yr, mo = parse_year_month(top_val_above)

            if yr and mo:
                cur_yr, cur_mo = yr, mo

            bottom_val = normalize_text(raw_df.iloc[metric_row, col_idx])
            metric = None
            if "аор" in bottom_val or "aop" in bottom_val or "план" in bottom_val:
                metric = "aop"
            elif "прогноз" in bottom_val or "forecast" in bottom_val:
                metric = "forecast"
            elif "факт" in bottom_val or "actual" in bottom_val:
                metric = "actual"

            if cur_yr and cur_mo and metric:
                month_cols.append({
                    "col_idx": col_idx,
                    "col_name": f"{cur_yr}-{cur_mo:02d}_{metric}"
                })

        if not month_cols:
            continue

        data_rows = []
        for r in range(metric_row + 1, len(raw_df)):
            article = normalize_article(raw_df.iloc[r, col_map["article"]] if "article" in col_map else None)
            client_raw = raw_df.iloc[r, col_map["client"]] if "client" in col_map else None

            if pd.isna(article) and pd.isna(client_raw):
                continue

            client_cleaned = clean_client_name(client_raw)

            supplier_str = str(raw_df.iloc[r, col_map["supplier"]]).strip() if "supplier" in col_map and pd.notna(raw_df.iloc[r, col_map["supplier"]]) else ""
            name_str = str(raw_df.iloc[r, col_map["name"]]).strip() if "name" in col_map and pd.notna(raw_df.iloc[r, col_map["name"]]) else ""

            price_val = None
            if "price" in col_map and pd.notna(raw_df.iloc[r, col_map["price"]]):
                try:
                    price_val = float(raw_df.iloc[r, col_map["price"]])
                except (ValueError, TypeError):
                    price_val = None

            row_dict = {
                "client": client_cleaned,
                "supplier": supplier_str if supplier_str else None,
                "product_name": name_str,
                "product_article": article,
                "price_cny": price_val,
                "manager": file_info["manager_name"]
            }

            for mc in month_cols:
                val = raw_df.iloc[r, mc["col_idx"]]
                row_dict[mc["col_name"]] = val

            data_rows.append(row_dict)

        if data_rows:
            sheet_df = pd.DataFrame(data_rows)
            sheet_df[["client", "supplier"]] = sheet_df[["client", "supplier"]].ffill()
            all_sheets_dfs.append(sheet_df)

    if not all_sheets_dfs:
        return pd.DataFrame()

    wide_df = pd.concat(all_sheets_dfs, ignore_index=True)
    return wide_df


def get_available_months(wide_df):
    """Возвращает список найденных периодов YYYY-MM."""
    months = set()
    if wide_df.empty:
        return []
    for col in wide_df.columns:
        match = MONTH_COLUMN_PATTERN.fullmatch(str(col))
        if match:
            months.add(match.group("month"))
    return sorted(list(months))


def transform_months(wide_df):
    """Разворачивает таблицу в формат с количественными и сумовыми денежными показателями."""
    if wide_df.empty:
        return pd.DataFrame(columns=FINAL_COLUMNS)

    months = get_available_months(wide_df)
    if not months:
        return pd.DataFrame(columns=FINAL_COLUMNS)

    final_rows = []

    for _, row in wide_df.iterrows():
        client = str(row.get("client", "") or "").strip()
        supplier = str(row.get("supplier", "") or "").strip()
        p_name = str(row.get("product_name", "") or "").strip()
        p_art = row.get("product_article", None)
        manager = str(row.get("manager", "") or "").strip()

        try:
            price = float(row.get("price_cny")) if pd.notna(row.get("price_cny")) else 0.0
        except (ValueError, TypeError):
            price = 0.0

        for m_str in months:
            yr_str, mo_str = m_str.split("-")
            yr = int(yr_str)
            mo_num = int(mo_str)

            aop_col = f"{m_str}_aop"
            forecast_col = f"{m_str}_forecast"
            actual_col = f"{m_str}_actual"

            def parse_num(v):
                try:
                    return float(v) if pd.notna(v) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            aop_pcs = parse_num(row.get(aop_col))
            forecast_pcs = parse_num(row.get(forecast_col))
            actual_pcs = parse_num(row.get(actual_col))

            # Расчет денежных показателей в юанях (Количество * Цена)
            aop_cny = aop_pcs * price
            forecast_cny = forecast_pcs * price
            actual_cny = actual_pcs * price

            final_rows.append({
                'AOP, шт': aop_pcs,
                'Прогноз, шт': forecast_pcs,
                'Факт, шт': actual_pcs,
                'AOP, юань, без НДС': round(aop_cny, 2),
                'Прогноз, юань, без НДС': round(forecast_cny, 2),
                'Факт, юань, без НДС': round(actual_cny, 2),
                'Ключ клиента': client,
                'Клиент': client,
                'Менеджер': manager,
                'Год': yr,
                'Поставщик': supplier,
                'Наименование': p_name,
                'Артикул': p_art,
                'Цена, юань, без НДС': price if price > 0 else None,
                'Месяц': MONTH_NAMES_RU.get(mo_num, ""),
                'Номер месяца': mo_num
            })

    res_df = pd.DataFrame(final_rows)
    res_df[['Ключ клиента', 'Клиент', 'Поставщик']] = res_df[['Ключ клиента', 'Клиент', 'Поставщик']].ffill()
    res_df = res_df[res_df['Артикул'].notna()].copy()

    return res_df[FINAL_COLUMNS]


def normalize_manager_file(file_path):
    """Сквозная обработка Excel-файла."""
    wide_df = prepare_wide_table(file_path)
    if wide_df.empty:
        return pd.DataFrame(columns=FINAL_COLUMNS)
    return transform_months(wide_df)