import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd, pytest
from app.engines.schema_profiler import profile
from app.services.analysis_service import run_question

SAMPLE = pathlib.Path(__file__).resolve().parents[2] / "sample_data"
@pytest.fixture(scope="module")
def emp():
    df = pd.read_csv(SAMPLE / "employees.csv"); return df, profile(df)
@pytest.fixture(scope="module")
def sales():
    df = pd.read_csv(SAMPLE / "sales.csv", parse_dates=["date"]); return df, profile(df)

def ask(d, q, lang="en"): return run_question(d[0], d[1], q, lang)

def test_count(emp):
    r = ask(emp, "how many rows are there?"); assert not r["error"] and r["result"]["rows"][0][0] == len(emp[0])

def test_average(emp):
    r = ask(emp, "what is the average salary?"); assert not r["error"]
    assert r["result"]["rows"][0][0] == round(emp[0].salary.mean(), 2)

def test_group(emp):
    r = ask(emp, "average salary by department"); assert r["plan"]["group_by"] == "department" and len(r["result"]["rows"]) == 5

def test_filter_and_group(sales):
    r = ask(sales, "total revenue by region where quantity > 5"); assert not r["error"]
    exp = sales[0][sales[0].quantity > 5].groupby("region").revenue.sum().round(2)
    assert {k: v for k, v in r["result"]["rows"]} == exp.to_dict()

def test_categorical_filter(sales):
    r = ask(sales, "total revenue in North"); assert r["result"]["rows"][0][0] == round(sales[0][sales[0].region == "North"].revenue.sum(), 2)

def test_top_n(sales):
    r = ask(sales, "top 3 products by revenue"); assert len(r["result"]["rows"]) == 3

def test_invalid_column(emp):
    r = ask(emp, "average bonus"); assert r["error"] and r["code"] == "invalid_column"

def test_unsupported(emp):
    for q in ("delete all rows", "tell me a joke"):
        r = ask(emp, q); assert r["error"] and r["code"] == "unsupported"

def test_ml_ops(sales):
    assert ask(sales, "forecast revenue for next months")["result"]["facts"]["kind"] == "forecast"
    assert ask(sales, "find outliers in revenue")["result"]["facts"]["kind"] == "anomalies"
    assert ask(sales, "segment the records into 4 clusters")["result"]["facts"]["k"] == 4
    assert ask(sales, "correlation between quantity and revenue")["result"]["facts"]["kind"] == "corr"

def test_hindi(emp):
    r = ask(emp, "salary ka ausat kitna hai", "hi"); assert not r["error"] and "औसत" in r["explanation"]
