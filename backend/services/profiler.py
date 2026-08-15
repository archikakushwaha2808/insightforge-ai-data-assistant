"""
Auto data-cleaning + profiling engine.
Mimics what you'd do manually in a Colab notebook:
  1. Detect column semantic types (numeric / categorical / datetime / text / boolean / id)
  2. Report + fix missing values, duplicates, mixed types
  3. Compute descriptive stats, outliers (IQR), correlations, skew/kurtosis
  4. Produce a clean DataFrame + a JSON-serializable profile report
"""
import pandas as pd
import numpy as np


def _safe_float(x) -> "float | None":
    """Casts to a plain Python float, converting NaN/inf to None since
    those aren't valid JSON and would break JSON.parse on the frontend."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(f) or np.isinf(f)) else f


def _infer_column_type(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "unknown"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    if pd.api.types.is_numeric_dtype(series):
        # Could still be an ID column (all-unique integers)
        if series.nunique() == len(series) and pd.api.types.is_integer_dtype(series):
            return "identifier"
        return "numeric"

    # try datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    try:
        parsed = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)
        if parsed.notna().mean() > 0.85:
            return "datetime"
    except Exception:
        pass

    # categorical vs free text
    unique_ratio = s.nunique() / max(len(s), 1)
    avg_len = s.astype(str).str.len().mean()
    if unique_ratio < 0.5 and s.nunique() <= 50:
        return "categorical"
    if avg_len > 40:
        return "text"
    return "categorical" if s.nunique() <= 100 else "text"


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Applies safe, standard cleaning steps. Returns (clean_df, log_of_actions)."""
    log = []
    df = df.copy()

    before_rows = len(df)
    df.drop_duplicates(inplace=True)
    if len(df) < before_rows:
        log.append(f"Removed {before_rows - len(df)} duplicate rows.")

    # Strip whitespace on object columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace({"nan": np.nan, "None": np.nan, "": np.nan})

    # Attempt numeric coercion on object columns that are "mostly numeric"
    for col in df.select_dtypes(include="object").columns:
        coerced = pd.to_numeric(df[col].str.replace(",", "", regex=False), errors="coerce")
        if coerced.notna().mean() > 0.9 and df[col].notna().mean() > 0:
            df[col] = coerced
            log.append(f"Converted column '{col}' to numeric.")

    # Attempt datetime coercion
    for col in df.select_dtypes(include="object").columns:
        try:
            parsed = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
            if parsed.notna().mean() > 0.85:
                df[col] = parsed
                log.append(f"Converted column '{col}' to datetime.")
        except Exception:
            continue

    # Impute missing values
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing == 0:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            median = df[col].median()
            df[col] = df[col].fillna(median)
            log.append(f"Filled {missing} missing values in '{col}' with median ({median:.2f}).")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            log.append(f"Left {missing} missing datetime values in '{col}' as-is.")
        else:
            mode = df[col].mode()
            fill_val = mode.iloc[0] if not mode.empty else "Unknown"
            df[col] = df[col].fillna(fill_val)
            log.append(f"Filled {missing} missing values in '{col}' with mode ('{fill_val}').")

    return df, log


def build_profile(df: pd.DataFrame) -> dict:
    """Builds a full JSON-serializable profile report."""
    col_types = {col: _infer_column_type(df[col]) for col in df.columns}

    columns_report = []
    for col in df.columns:
        ctype = col_types[col]
        entry = {
            "name": col,
            "type": ctype,
            "missing_count": int(df[col].isna().sum()),
            "missing_pct": round(float(df[col].isna().mean() * 100), 2),
            "unique_count": int(df[col].nunique()),
        }

        if ctype == "numeric":
            desc = df[col].describe()
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = df[(df[col] < lower) | (df[col] > upper)][col]
            entry.update({
                "mean": _safe_float(desc.get("mean", np.nan)),
                "std": _safe_float(desc.get("std", np.nan)),
                "min": _safe_float(desc.get("min", np.nan)),
                "max": _safe_float(desc.get("max", np.nan)),
                "median": _safe_float(df[col].median()),
                "sum": _safe_float(df[col].sum()),
                "skew": _safe_float(df[col].skew()),
                "kurtosis": _safe_float(df[col].kurtosis()),
                "outlier_count": int(len(outliers)),
            })
        elif ctype in ("categorical", "boolean", "identifier"):
            top = df[col].value_counts().head(5)
            entry["top_values"] = {str(k): int(v) for k, v in top.items()}
        elif ctype == "datetime":
            entry["min_date"] = str(df[col].min())
            entry["max_date"] = str(df[col].max())

        columns_report.append(entry)

    numeric_cols = [c for c, t in col_types.items() if t == "numeric"]
    correlation = None
    if len(numeric_cols) >= 2:
        corr_df = df[numeric_cols].corr(numeric_only=True).round(3)
        # .to_dict() leaves raw numpy.float64 values (not JSON-serializable)
        # and NaN (not valid JSON) for constant/all-missing columns — cast
        # every cell to a plain float or None explicitly.
        correlation = {
            col: {row: _safe_float(val) for row, val in corr_df[col].items()}
            for col in corr_df.columns
        }

    profile = {
        "n_rows": int(len(df)),
        "n_cols": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing_cells": int(df.isna().sum().sum()),
        "columns": columns_report,
        "numeric_columns": numeric_cols,
        "categorical_columns": [c for c, t in col_types.items() if t == "categorical"],
        "datetime_columns": [c for c, t in col_types.items() if t == "datetime"],
        "correlation_matrix": correlation,
    }
    return profile
