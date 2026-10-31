import pandas as pd
from ..domain.data_analysis import AnalysisError

def load_dataframe(path: str) -> pd.DataFrame:
    p = str(path).lower()
    try:
        if p.endswith(".csv"):
            try: df = pd.read_csv(path)
            except UnicodeDecodeError: df = pd.read_csv(path, encoding="latin-1")
        elif p.endswith(".xlsx"):
            df = pd.read_excel(path, engine="openpyxl")
        else:
            raise AnalysisError("Only .csv and .xlsx files are supported.", "unsupported_file")
    except AnalysisError:
        raise
    except Exception as e:
        raise AnalysisError(f"Could not read the file: {e}", "bad_file")
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object and "date" in c.lower():
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().mean() > 0.9:
                df[c] = parsed
    return df

def validate_schema(df: pd.DataFrame):
    if df.empty or len(df.columns) < 1:
        raise AnalysisError("The file has no data.", "empty")
    if df.columns.duplicated().any():
        raise AnalysisError("Duplicate column names found. Please rename them.", "duplicate_columns")

def column_kind(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s): return "categorical"
    if pd.api.types.is_numeric_dtype(s): return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s): return "datetime"
    return "categorical" if s.nunique() <= max(50, 0.3 * len(s)) else "text"

def profile(df: pd.DataFrame) -> dict:
    cols = []
    for c in df.columns:
        s, kind = df[c], column_kind(df[c])
        info = {"name": c, "kind": kind, "missing": int(s.isna().sum()), "unique": int(s.nunique()),
                "sample": [str(v) for v in s.dropna().unique()[:3]]}
        if kind == "numeric":
            info.update(min=float(s.min()), max=float(s.max()), mean=round(float(s.mean()), 2))
        cols.append(info)
    return {"rows": int(len(df)), "n_columns": len(cols), "columns": cols}
