"""Deterministic pandas / scikit-learn execution. Only whitelisted operations run; no eval/exec."""
import operator
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from ..domain.data_analysis import AnalysisError, AnalysisPlan, AnalysisResult, Op

CMP = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le}

def _py(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return None if np.isnan(v) else round(float(v), 2)
    if isinstance(v, pd.Timestamp): return v.strftime("%Y-%m-%d")
    if isinstance(v, np.bool_): return bool(v)
    return v

def _rows(df): return [[_py(v) for v in r] for r in df.itertuples(index=False)]

def col(df, name, numeric=False):
    if not name or name not in df.columns:
        raise AnalysisError(f"Column '{name}' was not found. Available columns: {', '.join(map(str, df.columns))}", "invalid_column")
    if numeric and (pd.api.types.is_bool_dtype(df[name]) or not pd.api.types.is_numeric_dtype(df[name])):
        raise AnalysisError(f"Column '{name}' is not numeric, so this calculation is not possible.", "not_numeric")
    return name

def apply_filters(df, filters):
    for f in filters:
        c = col(df, f.column); s = df[c]; v = f.value
        if f.op == "contains":
            m = s.astype(str).str.contains(str(v), case=False, regex=False)
        else:
            try:
                if pd.api.types.is_numeric_dtype(s): v = float(v)
                elif pd.api.types.is_datetime64_any_dtype(s): v = pd.Timestamp(v)
                else: s, v = s.astype(str).str.lower(), str(v).lower()
                m = CMP[f.op](s, v)
            except (ValueError, TypeError):
                raise AnalysisError(f"Cannot compare column '{c}' with value '{v}'.", "bad_filter")
        df = df[m]
    return df

def _group_result(op, title, t, g, v, chart_type="bar"):
    t = t.copy(); t[v] = t[v].round(2)
    vals = [float(x) for x in t[v]]
    best, worst = int(np.argmax(vals)), int(np.argmin(vals))
    labels = [str(x) for x in t[g]]
    return AnalysisResult(operation=op, title=title, columns=[g, v], rows=_rows(t),
        chart={"type": chart_type, "labels": labels[:30], "series": [{"name": v, "values": vals[:30]}]},
        facts={"kind": "groups", "group": g, "measure": v, "best": [labels[best], vals[best]],
               "worst": [labels[worst], vals[worst]], "count": len(t)}, numbers=vals)

def _count(df, p):
    if p.group_by:
        g = col(df, p.group_by)
        t = df.groupby(g).size().sort_values(ascending=False).reset_index(name="count")
        return _group_result(p.operation, f"Row count by {g}", t, g, "count")
    n = int(len(df))
    return AnalysisResult(operation=p.operation, title="Row count", columns=["rows"], rows=[[n]],
        facts={"kind": "scalar", "label": "rows", "agg": "count", "value": n}, numbers=[n])

def _aggregate(df, p):
    c = col(df, p.column, True)
    if p.group_by:
        g = col(df, p.group_by)
        t = df.groupby(g)[c].agg(p.agg).reset_index().sort_values(c, ascending=False)
        return _group_result(p.operation, f"{p.agg} of {c} by {g}", t, g, c)
    v = _py(getattr(df[c], p.agg)())
    return AnalysisResult(operation=p.operation, title=f"{p.agg} of {c}", columns=[c], rows=[[v]],
        facts={"kind": "scalar", "label": c, "agg": p.agg, "value": v}, numbers=[v])

def _top(df, p):
    c = col(df, p.column, True)
    if p.group_by:
        g = col(df, p.group_by)
        t = df.groupby(g)[c].agg(p.agg).reset_index()
        t = t.sort_values(c, ascending=p.ascending).head(p.n)
        return _group_result(p.operation, f"{'Bottom' if p.ascending else 'Top'} {p.n} {g} by {c}", t, g, c)
    t = df.sort_values(c, ascending=p.ascending).head(p.n)
    show = t[list(t.columns[:8])] if c in t.columns[:8] else t[[*t.columns[:7], c]]
    return AnalysisResult(operation=p.operation, title=f"{'Bottom' if p.ascending else 'Top'} {p.n} rows by {c}",
        columns=list(show.columns), rows=_rows(show), facts={"kind": "table", "title": f"{'Bottom' if p.ascending else 'Top'} {p.n} rows by {c}", "n": len(show)},
        numbers=[float(x) for x in t[c]])

def _value_counts(df, p):
    c = col(df, p.column or p.group_by)
    t = df[c].value_counts().head(p.n if p.n > 5 else 20).reset_index(); t.columns = [c, "count"]
    return _group_result(p.operation, f"Distribution of {c}", t, c, "count")

def _describe(df, p):
    d = df.describe().T.reset_index(); d.columns = ["column"] + list(d.columns[1:])
    if d.empty: raise AnalysisError("No numeric columns to summarize.", "no_numeric")
    nums = [float(x) for x in d[["count", "mean", "min", "max"]].to_numpy().flatten() if pd.notna(x)]
    return AnalysisResult(operation=p.operation, title="Summary statistics", columns=list(d.columns), rows=_rows(d),
        facts={"kind": "table", "title": "Summary statistics", "n": len(d)}, numbers=nums)

def _numeric_cols(df): return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]

def _corr(df, p):
    nums = _numeric_cols(df)
    if p.column and p.target:
        a, b = col(df, p.column, True), col(df, p.target, True); pairs = [(a, b, df[a].corr(df[b]))]
    else:
        if len(nums) < 2: raise AnalysisError("Need at least two numeric columns for correlation.", "no_numeric")
        m = df[nums].corr()
        pairs = [(a, b, m.loc[a, b]) for i, a in enumerate(nums) for b in nums[i + 1:] if pd.notna(m.loc[a, b])]
        pairs = sorted(pairs, key=lambda x: -abs(x[2]))[:10]
    pairs = [(a, b, round(float(r), 3)) for a, b, r in pairs]
    return AnalysisResult(operation=p.operation, title="Correlation", columns=["column_a", "column_b", "correlation"],
        rows=[list(x) for x in pairs],
        chart={"type": "bar", "labels": [f"{a} vs {b}" for a, b, _ in pairs], "series": [{"name": "correlation", "values": [r for *_, r in pairs]}]},
        facts={"kind": "corr", "a": pairs[0][0], "b": pairs[0][1], "r": pairs[0][2]}, numbers=[r for *_, r in pairs])

def _forecast(df, p):
    c = col(df, p.column, True)
    dt = next((x for x in df.columns if pd.api.types.is_datetime64_any_dtype(df[x])), None)
    if not dt: raise AnalysisError("Forecasting needs a date column, but none was found in this dataset.", "no_date")
    s = df.set_index(dt)[c].resample("MS").agg("sum").dropna()
    last = df[dt].max()
    if last.normalize() < (last + pd.offsets.MonthEnd(0)).normalize():
        s = s.iloc[:-1]
    if len(s) < 4: raise AnalysisError("Need at least 4 months of data to forecast.", "too_little_data")
    X = np.arange(len(s)).reshape(-1, 1); m = LinearRegression().fit(X, s.values)
    pred = m.predict(np.arange(len(s), len(s) + 3).reshape(-1, 1)); r2 = float(m.score(X, s.values))
    hist = [d.strftime("%Y-%m") for d in s.index]
    fut = [(s.index[-1] + pd.DateOffset(months=i)).strftime("%Y-%m") for i in (1, 2, 3)]
    hv, pv = [round(float(x), 2) for x in s.values], [round(float(x), 2) for x in pred]
    rows = [[l, v, "actual"] for l, v in zip(hist, hv)] + [[l, v, "forecast"] for l, v in zip(fut, pv)]
    slope = round(float(m.coef_[0]), 2)
    return AnalysisResult(operation=p.operation, title=f"Monthly {c} trend and 3-month forecast", columns=["month", c, "type"], rows=rows,
        chart={"type": "line", "labels": hist + fut, "series": [
            {"name": "Actual", "values": hv + [None] * 3}, {"name": "Forecast", "values": [None] * (len(hv) - 1) + [hv[-1]] + pv}]},
        facts={"kind": "forecast", "measure": c, "slope": slope, "up": slope >= 0, "next": pv[0], "r2": round(r2, 2)},
        numbers=hv + pv + [slope, round(r2, 2)])

def _anomalies(df, p):
    cols = [col(df, p.column, True)] if p.column else [c for c in _numeric_cols(df) if df[c].nunique() < len(df)][:6]
    X = df[cols].dropna()
    if len(X) < 20: raise AnalysisError("Need at least 20 rows to detect anomalies.", "too_little_data")
    iso = IsolationForest(contamination=0.03, random_state=42).fit(X)
    score, flag = -iso.score_samples(X), iso.predict(X) == -1
    out = df.loc[X.index[flag]].assign(anomaly_score=np.round(score[flag], 3)).sort_values("anomaly_score", ascending=False).head(15)
    show = out[[*out.columns[:7], "anomaly_score"]] if out.shape[1] > 8 else out
    return AnalysisResult(operation=p.operation, title="Anomalies (Isolation Forest)", columns=list(show.columns), rows=_rows(show),
        facts={"kind": "anomalies", "found": int(flag.sum()), "total": len(X), "cols": cols},
        numbers=[int(flag.sum()), len(X)] + [float(x) for x in out["anomaly_score"]])

def _clusters(df, p):
    cols = [c for c in _numeric_cols(df) if df[c].nunique() < len(df)][:8]
    X = df[cols].dropna()
    if len(cols) < 2 or len(X) < 20: raise AnalysisError("Need at least 2 numeric columns and 20 rows for clustering.", "too_little_data")
    Z = StandardScaler().fit_transform(X); km = KMeans(n_clusters=p.k, n_init=10, random_state=42).fit(Z)
    sil = round(float(silhouette_score(Z, km.labels_, sample_size=min(1000, len(Z)), random_state=42)), 2)
    prof = X.assign(cluster=km.labels_).groupby("cluster").agg(["mean"]).round(2); prof.columns = cols
    prof.insert(0, "size", np.bincount(km.labels_)); prof = prof.reset_index()
    sizes = [int(x) for x in prof["size"]]
    return AnalysisResult(operation=p.operation, title=f"Customer/record segments (KMeans, k={p.k})", columns=list(prof.columns), rows=_rows(prof),
        chart={"type": "bar", "labels": [f"Cluster {i}" for i in prof["cluster"]], "series": [{"name": "size", "values": sizes}]},
        facts={"kind": "clusters", "k": p.k, "sizes": sizes, "silhouette": sil},
        numbers=[float(x) for x in sizes] + [sil] + [float(x) for x in prof[cols].to_numpy().flatten()])

HANDLERS = {Op.count_rows: _count, Op.aggregate: _aggregate, Op.top_n: _top, Op.value_counts: _value_counts,
            Op.describe: _describe, Op.correlation: _corr, Op.forecast: _forecast, Op.anomalies: _anomalies, Op.clusters: _clusters}

def execute(df: pd.DataFrame, plan: AnalysisPlan) -> AnalysisResult:
    df = apply_filters(df, plan.filters)
    if len(df) == 0: raise AnalysisError("No rows match the given filters.", "empty_result")
    return HANDLERS[plan.operation](df, plan)