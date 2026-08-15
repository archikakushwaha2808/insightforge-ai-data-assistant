"""
Loads any of: .csv, .tsv, .txt, .xlsx, .xls, .json into a clean pandas DataFrame.
Handles messy real-world files: unknown delimiters, encodings, stray BOMs, mixed types.
"""
import pandas as pd
import chardet
import io
import os


def _detect_encoding(raw: bytes) -> str:
    result = chardet.detect(raw[:200_000])
    return result.get("encoding") or "utf-8"


def load_dataframe(file_path: str, original_filename: str) -> pd.DataFrame:
    ext = os.path.splitext(original_filename)[1].lower()

    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)

    elif ext == ".json":
        df = pd.read_json(file_path)

    elif ext in (".csv", ".tsv", ".txt"):
        with open(file_path, "rb") as f:
            raw = f.read()
        encoding = _detect_encoding(raw)
        text = raw.decode(encoding, errors="replace")

        # Try to auto-detect delimiter among common candidates
        sample = text[:5000]
        candidates = [",", "\t", ";", "|"]
        counts = {c: sample.count(c) for c in candidates}
        delimiter = max(counts, key=counts.get) if max(counts.values()) > 0 else ","

        df = pd.read_csv(io.StringIO(text), sep=delimiter, engine="python", on_bad_lines="skip")

    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]
    return df
