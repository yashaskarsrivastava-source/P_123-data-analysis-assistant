"""Pipeline: profile -> interpret (LLM planner or ML router) -> validate plan -> pandas/ML compute -> explain (LLM) -> numeric validation."""
import json, re
import pandas as pd
from pydantic import ValidationError
from ..domain.data_analysis import AnalysisError, AnalysisPlan, AnalysisResult, Op
from ..engines.operations import execute
from ..engines.router import plan_from_question
from . import llm

LANGS = {"en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French"}
AGGW = {"en": {"mean": "average", "sum": "total", "min": "minimum", "max": "maximum", "median": "median"},
        "hi": {"mean": "औसत", "sum": "कुल", "min": "न्यूनतम", "max": "अधिकतम", "median": "माध्यिका"}}
TPL = {
 "en": {"count": "There are {value:,} rows matching your question.", "scalar": "The {agg} of {label} is {value:,}.",
        "groups": "Across {count} values of {group}, '{b}' has the highest {measure} ({bv:,}) and '{w}' has the lowest ({wv:,}).",
        "table": "{title}: showing {n} rows below.", "forecast": "{measure} shows an {dir} trend of about {slope:,} per month (R²={r2}). Forecast for next month: {next:,}.",
        "anomalies": "{found} unusual records out of {total} were flagged by Isolation Forest.",
        "clusters": "The data was split into {k} clusters of sizes {sizes} (silhouette score {sil}).",
        "corr": "The strongest relationship is between {a} and {b} (correlation {r})."},
 "hi": {"count": "आपके प्रश्न से मेल खाती {value:,} पंक्तियां हैं।", "scalar": "{label} का {agg} {value:,} है।",
        "groups": "{group} के {count} मानों में, '{b}' का {measure} सबसे अधिक ({bv:,}) और '{w}' का सबसे कम ({wv:,}) है।",
        "table": "{title}: नीचे {n} पंक्तियां दिखाई गई हैं।", "forecast": "{measure} में लगभग {slope:,} प्रति माह का {dir} रुझान है (R²={r2})। अगले महीने का पूर्वानुमान: {next:,}।",
        "anomalies": "Isolation Forest ने {total} में से {found} असामान्य रिकॉर्ड पाए।",
        "clusters": "डेटा को {k} क्लस्टर में बांटा गया, आकार {sizes} (silhouette {sil})।",
        "corr": "सबसे मजबूत संबंध {a} और {b} के बीच है (correlation {r})।"}}

def template_explain(res: AnalysisResult, lang: str) -> str:
    t, f = TPL.get(lang, TPL["en"]), res.facts
    L = lang if lang in TPL else "en"; k = f.get("kind")
    if k == "scalar":
        return t["count"].format(**f) if f["agg"] == "count" else t["scalar"].format(agg=AGGW[L][f["agg"]], label=f["label"], value=f["value"])
    if k == "groups": return t["groups"].format(b=f["best"][0], bv=f["best"][1], w=f["worst"][0], wv=f["worst"][1], **{x: f[x] for x in ("count", "group", "measure")})
    if k == "forecast":
        d = {"en": ("upward", "downward"), "hi": ("बढ़ते", "घटते")}[L][0 if f["up"] else 1]
        return t["forecast"].format(dir=d, **{x: f[x] for x in ("measure", "slope", "r2", "next")})
    if k == "anomalies": return t["anomalies"].format(found=f["found"], total=f["total"])
    if k == "clusters": return t["clusters"].format(k=f["k"], sizes=", ".join(map(str, f["sizes"])), sil=f["silhouette"])
    if k == "corr": return t["corr"].format(a=f["a"], b=f["b"], r=f["r"])
    return t["table"].format(title=f.get("title", res.title), n=f.get("n", len(res.rows)))

NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
def validate_numbers(text: str, res: AnalysisResult, plan: AnalysisPlan) -> bool:
    allowed = [float(x) for x in res.numbers] + [plan.n, plan.k, len(res.rows)] + [float(x) for x in re.findall(r"\d+", json.dumps(res.facts))]
    for tok in NUM.findall(text):
        try: v = float(tok.replace(",", "").rstrip("."))
        except ValueError: continue
        if not any(abs(v - a) <= max(0.011, 0.005 * abs(a)) for a in allowed): return False
    return True

def llm_explain(question, res, lang):
    system = (f"You are a data analyst. Explain the computed result in {LANGS.get(lang, 'English')} in 2-3 short sentences. "
              "Use ONLY numbers that appear in the JSON result. Do not compute new numbers or percentages.")
    return llm.complete(system, json.dumps({"question": question, "title": res.title, "facts": res.facts, "rows": res.rows[:10]}, default=str), 300)

# ---------- follow-up "explain this" support ----------
EXPLAIN_WORDS = re.compile(
    r"\b(explain|explanation|summari[sz]e|elaborate|interpret|why|samjha\w*|samajh\w*|batao|bata do|matlab|isko|isse)\b|समझा|व्याख्या|क्यों|मतलब|बताओ",
    re.I)

def is_followup_explain(question: str) -> bool:
    q = question.strip().lower()
    return len(q.split()) <= 8 and bool(EXPLAIN_WORDS.search(q))

def explain_previous(question: str, prev_result: dict, lang: str) -> dict | None:
    """Explain the previous result without recomputing anything. Returns an API-shaped dict or None."""
    if not prev_result or not prev_result.get("result"): return None
    prev = prev_result["result"]
    engine = {"planner": "followup", "explainer": "template", "validated": True, "llm_rejected": False, "confidence": None}
    text = None
    if llm.available():
        system = (f"You are a data analyst. The user asks a follow-up about a result that was ALREADY computed. "
                  f"Answer in {LANGS.get(lang, 'English')} in 3-4 short sentences. Use ONLY numbers that appear in the JSON. "
                  "Do not compute new numbers or percentages. Do not invent causes you cannot see in the data.")
        payload = {"user_question": question, "title": prev.get("title"), "facts": prev.get("facts"), "rows": (prev.get("rows") or [])[:15]}
        text = llm.complete(system, json.dumps(payload, default=str), 400)
        if text:
            allowed = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", json.dumps(payload, default=str))]
            ok = True
            for tok in NUM.findall(text):
                try: v = float(tok.replace(",", "").rstrip("."))
                except ValueError: continue
                if not any(abs(v - a) <= max(0.011, 0.005 * abs(a)) for a in allowed): ok = False; break
            if ok: engine["explainer"] = "llm"
            else: engine["llm_rejected"], text = True, None
    if not text:
        try: text = template_explain(AnalysisResult(**prev), lang)
        except Exception: text = prev.get("title") or "Here is the previous result."
    return {"error": False, "explanation": text, "engine": engine, "plan": prev_result.get("plan"), "result": None}

def llm_plan(question, profile, df, prev):
    system = ("Convert the question into ONE JSON analysis plan. Output ONLY JSON. Keys: operation (count_rows|aggregate|top_n|value_counts|describe|"
              "correlation|forecast|anomalies|clusters|unsupported), column, agg (sum|mean|min|max|median), group_by, filters [{column, op(==,!=,>,<,>=,<=,contains), value}], "
              "n, k, target, ascending. Use only the listed columns. Questions asking to modify data or unrelated to the data -> {\"operation\":\"unsupported\"}.")
    out = llm.complete(system, json.dumps({"columns": [(c["name"], c["kind"]) for c in profile["columns"]], "question": question, "previous_plan": prev}), 400)
    if not out: return None
    try:
        d = json.loads(out[out.index("{"): out.rindex("}") + 1])
        if d.get("operation") == "unsupported":
            raise AnalysisError("This request isn't supported. I only analyse your data; I never modify it.", "unsupported")
        plan = AnalysisPlan(**{k: v for k, v in d.items() if v is not None})
        used = [plan.column, plan.group_by, plan.target] + [f.column for f in plan.filters]
        return plan if all(u is None or u in df.columns for u in used) else None
    except AnalysisError: raise
    except (ValueError, ValidationError, TypeError): return None

def run_question(df: pd.DataFrame, profile: dict, question: str, language: str = "en",
                 prev_plan: dict | None = None, prev_output: dict | None = None) -> dict:
    # follow-up like "explain this": reuse the last result, no new computation
    if prev_output and is_followup_explain(question):
        out = explain_previous(question, prev_output, language)
        if out: return out
    engine = {"planner": None, "explainer": "template", "validated": True, "llm_rejected": False, "confidence": None}
    try:
        plan = llm_plan(question, profile, df, prev_plan) if llm.available() else None
        if plan: engine["planner"] = "llm"
        else:
            plan, conf = plan_from_question(question, df, prev_plan)
            engine.update(planner="ml-router", confidence=round(conf, 2))
        res = execute(df, plan)
    except AnalysisError as e:
        return {"error": True, "code": e.code, "explanation": e.message, "engine": engine, "plan": None, "result": None}
    text = llm_explain(question, res, language) if llm.available() else None
    if text:
        if validate_numbers(text, res, plan): engine["explainer"] = "llm"
        else: engine["llm_rejected"], text = True, None
    return {"error": False, "explanation": text or template_explain(res, language), "engine": engine,
            "plan": plan.model_dump(mode="json"), "result": res.model_dump(mode="json")}