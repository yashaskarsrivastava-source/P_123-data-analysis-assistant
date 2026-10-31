"""Hybrid operation router: ML intent classifier (TF-IDF + Logistic Regression, trained on English/Hindi/Hinglish
seed phrases) + rule-based entity extraction against the real schema. Output is always a validated AnalysisPlan."""
import difflib, re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from ..domain.data_analysis import AnalysisError, AnalysisPlan, Filter, Op
from .schema_profiler import column_kind

SEEDS = {
 "count_rows": ["how many rows are there", "count the records", "total number of orders", "kitni rows hain", "kitne records hai", "number of employees in each department", "count of customers by region", "कितनी पंक्तियां हैं", "कुल कितने ऑर्डर हैं", "how many students scored above 80", "how many entries"],
 "aggregate": ["average salary", "what is the mean revenue", "total sales by region", "sum of quantity", "maximum price", "minimum age", "median salary by department", "average revenue per category", "ausat salary kitni hai", "औसत वेतन क्या है", "kul revenue region wise", "mean rating for each product", "what is the total revenue"],
 "top_n": ["top 5 products by revenue", "which region has the highest sales", "bottom 3 departments by salary", "best performing category", "top 10 customers", "sabse zyada revenue wala product", "sabse kam salary kis department me", "highest paid employees", "सबसे ज्यादा बिक्री वाला क्षेत्र", "lowest rated product", "which category earns the most"],
 "value_counts": ["distribution of region", "show value counts of category", "frequency of each product", "breakdown of departments", "category wise distribution", "unique values in product", "how many of each category", "region ka distribution", "show frequency of values"],
 "describe": ["describe the dataset", "summary statistics", "give me an overview of the data", "data ka summary dikhao", "dataset ke bare me batao", "statistics of all columns", "डेटा का सारांश दिखाओ", "profile the data", "summarize this data"],
 "correlation": ["correlation between price and quantity", "which columns are related", "relationship between study hours and marks", "kaun se columns related hain", "correlation matrix", "does experience affect salary", "सहसंबंध दिखाओ", "dependency between variables", "is salary related to age"],
 "forecast": ["forecast revenue for next months", "predict future sales", "trend of revenue over time", "monthly sales trend", "next month ka prediction", "sales ka trend dikhao", "भविष्य की बिक्री का पूर्वानुमान", "will sales increase", "revenue over time", "predict next quarter revenue"],
 "anomalies": ["find outliers in salary", "detect anomalies", "unusual orders", "any abnormal values", "outlier detect karo", "gadbad wali entries dikhao", "असामान्य मान खोजो", "suspicious transactions", "show outliers"],
 "clusters": ["segment customers into groups", "cluster the data", "group similar employees", "find 3 clusters", "customer segmentation", "similar students group karo", "डेटा को समूहों में बांटो", "kmeans clustering", "segment the records"],
 "unsupported": ["delete all rows", "drop the table", "send an email to the manager", "what is the weather today", "tell me a joke", "who is the prime minister", "write python code to hack", "update the salary of employee", "modify the dataset", "predict stock market tomorrow", "dataset delete kar do", "mausam kaisa hai", "मुझे एक चुटकुला सुनाओ", "hello how are you", "remove the first column", "run this sql query"],
}
_X = [s for v in SEEDS.values() for s in v]; _y = [k for k, v in SEEDS.items() for _ in v]
_clf = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True), LogisticRegression(C=20, max_iter=1000)).fit(_X, _y)

def classify(q: str):
    p = _clf.predict_proba([q])[0]; i = p.argmax()
    return _clf.classes_[i], float(p[i])

ALIASES = {"revenue": ["sales", "income", "turnover", "बिक्री", "कमाई"], "salary": ["pay", "wage", "vetan", "वेतन", "तनख्वाह"],
           "quantity": ["qty", "units"], "age": ["umar", "उम्र"], "rating": ["stars"], "experience years": ["experience"],
           "study hours": ["study time"], "attendance": ["hazri"], "customer age": ["customers age"]}
AGG_KW = {"mean": ["average", "avg", "mean", "ausat", "औसत"], "sum": ["total", "sum", "kul", "कुल"],
          "max": ["maximum", "highest", "largest", "biggest", "max", "अधिकतम", "सबसे ज्यादा"], "min": ["minimum", "lowest", "smallest", "min", "न्यूनतम", "सबसे कम"],
          "median": ["median", "माध्यिका"]}
GROUP_KW = [r"\bby\b", r"\bper\b", r"\beach\b", r"\bevery\b", r"\bacross\b", r"\bhar\b", r"के अनुसार", r"प्रत्येक", r"हर ", r"ke hisab se", r"wise"]
ASC_KW = ["lowest", "bottom", "least", "smallest", "worst", "sabse kam", "सबसे कम", "minimum"]
STOP = set("the a an of for in to is are what which how many much by per each column data dataset all".split())
CMP_WORDS = {"greater than": ">", "more than": ">", "above": ">", "over": ">", "less than": "<", "below": "<", "under": "<", "equal to": "=="}

def _term_re(t):
    return re.compile((rf"(?<!\w){re.escape(t)}(?:s|es)?(?!\w)") if t.isascii() else re.escape(t))

def find_columns(q, df):
    found = []
    for c in df.columns:
        norm = c.lower().replace("_", " ")
        for t in [norm] + ALIASES.get(norm, []):
            m = _term_re(t).search(q)
            if m: found.append((m.start(), m.end(), c)); break
    found = [f for f in found if not any(o is not f and o[0] <= f[0] and f[1] <= o[1] and (o[1] - o[0]) > (f[1] - f[0]) for o in found)]
    return sorted(found)

def _unknown_column(q, df):
    m = re.search(r"(?:average|mean|sum|total|max|maximum|min|minimum|median|highest|lowest|of|for|ausat|kul)\s+(?:the\s+)?([a-z_][\w]*)", q)
    if not m or m.group(1) in STOP: return None
    w = m.group(1)
    for c in df.columns:
        if w in c.lower().replace("_", " ").split(): return c
    close = difflib.get_close_matches(w, [c.lower() for c in df.columns], n=1, cutoff=0.75)
    if close: return next(c for c in df.columns if c.lower() == close[0])
    raise AnalysisError(f"Column '{w}' was not found. Available columns: {', '.join(df.columns)}", "invalid_column")

def plan_from_question(question: str, df: pd.DataFrame, prev: dict | None = None):
    q = question.lower().replace("_", " ").strip()
    op, conf = classify(q)
    if op == "unsupported" or conf < 0.22:
        raise AnalysisError("This request isn't supported. I can count, average/sum/min/max/median, rank top-N, show distributions, "
                            "summary statistics, correlations, forecasts, anomalies and clusters. I never modify your data.", "unsupported")
    kinds = {c: column_kind(df[c]) for c in df.columns}
    mentions = find_columns(q, df)
    # numeric filters
    filters, filter_cols = [], set()
    for c in [c for c in df.columns if kinds[c] == "numeric"]:
        norm = re.escape(c.lower().replace("_", " "))
        words = "|".join(map(re.escape, CMP_WORDS))
        m = re.search(rf"{norm}\s*(?:is|are)?\s*(>=|<=|==|>|<|=|{words})\s*(-?\d+(?:\.\d+)?)", q)
        if m:
            o = m.group(1); o = CMP_WORDS.get(o, "==" if o == "=" else o)
            filters.append(Filter(column=c, op=o, value=float(m.group(2)))); filter_cols.add(c)
    # categorical value filters
    for c in [c for c in df.columns if kinds[c] == "categorical" and df[c].nunique() <= 100]:
        for v in df[c].dropna().unique():
            if isinstance(v, str) and re.search(rf"(?<!\w){re.escape(v.lower())}(?!\w)", q):
                filters.append(Filter(column=c, op="==", value=v)); filter_cols.add(c)
    mentions = [m for m in mentions if m[2] not in filter_cols or kinds[m[2]] != "categorical"]
    # group-by
    group = None
    for kw in GROUP_KW:
        m = re.search(kw, q)
        if not m: continue
        cands = [x for x in mentions if x[1] <= m.start()] if kw == "wise" else [x for x in mentions if x[0] >= m.end()]
        if cands:
            group = (cands[-1] if kw == "wise" else cands[0])[2]; break
    cat_mentions = [x[2] for x in mentions if kinds[x[2]] == "categorical" and x[2] not in filter_cols]
    if group and kinds[group] == "numeric":
        group = cat_mentions[0] if cat_mentions else None
    if not group and op in ("top_n",) and cat_mentions: group = cat_mentions[0]
    nums = [x[2] for x in mentions if kinds[x[2]] == "numeric" and x[2] not in filter_cols and x[2] != group]
    measure = nums[0] if nums else None
    # agg
    agg, best = "mean", 10**9
    for a, kws in AGG_KW.items():
        for k in kws:
            i = q.find(k)
            if 0 <= i < best: agg, best = a, i
    if best == 10**9: agg = "sum" if (group and op in ("top_n", "aggregate")) else "mean"
    n = 1 if re.search(r"\b(which|kaun|kaunsa|kis)\b", q) else 5
    m = re.search(r"(?:top|bottom|first|best|worst|lowest|highest)\s*(\d+)|(\d+)\s*(?:top|best)", q)
    if m: n = int(m.group(1) or m.group(2))
    k = 3
    m = re.search(r"(\d+)\s*(?:clusters|groups|segments)|k\s*=\s*(\d+)", q)
    if m: k = min(8, max(2, int(m.group(1) or m.group(2))))
    ascending = any(w in q for w in ASC_KW)
    target = nums[1] if len(nums) > 1 else None
    needs_measure = op in ("aggregate", "top_n", "forecast")
    if needs_measure and not measure:
        measure = _unknown_column(q, df)
        if not measure and prev and prev.get("column") in df.columns: measure = prev["column"]
    if op == "top_n" and not measure and group: op = "value_counts"
    if needs_measure and not measure and op != "value_counts":
        raise AnalysisError("Which column should I use? Available columns: " + ", ".join(df.columns), "missing_column")
    if op == "forecast" and not measure and prev: measure = prev.get("column")
    if op in ("anomalies", "clusters", "value_counts") and not measure and nums: measure = nums[0] if op == "anomalies" else None
    column = measure
    if op == "value_counts": column = group or (cat_mentions[0] if cat_mentions else None)
    if op == "value_counts" and not column: raise AnalysisError("Which column's distribution should I show?", "missing_column")
    if op == "correlation": column, target = (nums + [None, None])[:2]
    plan = AnalysisPlan(operation=Op(op), column=column, agg=agg, group_by=group if op not in ("value_counts",) else None,
                        filters=filters, n=n, k=k, target=target, ascending=ascending)
    return plan, conf
