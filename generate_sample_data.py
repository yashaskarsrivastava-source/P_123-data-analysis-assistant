"""Generates the 3 sample datasets used by the app (python generate_sample_data.py)."""
import numpy as np, pandas as pd
rng = np.random.default_rng(42)

n = 900
d = pd.DataFrame({"order_id": range(1001, 1001 + n),
  "date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 640, n), "D"),
  "region": rng.choice(["North", "South", "East", "West"], n, p=[.3, .25, .2, .25]),
  "category": rng.choice(["Electronics", "Clothing", "Grocery", "Furniture"], n, p=[.3, .3, .25, .15])})
d["product"] = [rng.choice({"Electronics": ["Laptop", "Phone", "Headphones"], "Clothing": ["Jeans", "Jacket", "Shirt"],
                "Grocery": ["Rice", "Oil", "Tea"], "Furniture": ["Chair", "Table", "Sofa"]}[c]) for c in d.category]
d["quantity"] = rng.integers(1, 11, n)
base = {"Electronics": 450, "Clothing": 60, "Grocery": 15, "Furniture": 220}
d["unit_price"] = [round(base[c] * rng.uniform(.8, 1.2), 2) for c in d.category]
d["discount"] = rng.choice([0, 5, 10, 15, 20], n)
d["revenue"] = (d.quantity * d.unit_price * (1 - d.discount / 100) * (1 + (d.date - d.date.min()).dt.days / 1500)).round(2)
d["customer_age"] = rng.integers(18, 70, n)
d["rating"] = np.clip(rng.normal(4, .8, n), 1, 5).round(1)
d.loc[rng.choice(n, 8, replace=False), "revenue"] *= 12   # planted anomalies
d.sort_values("date").to_csv("sample_data/sales.csv", index=False)

m = 320
e = pd.DataFrame({"emp_id": range(5001, 5001 + m), "department": rng.choice(["Engineering", "Sales", "HR", "Finance", "Support"], m, p=[.35, .25, .1, .1, .2]),
  "city": rng.choice(["Delhi", "Mumbai", "Bangalore", "Pune", "Noida"], m), "age": rng.integers(22, 60, m)})
e["experience_years"] = np.clip(e.age - 22 - rng.integers(0, 6, m), 0, None)
b = {"Engineering": 60000, "Sales": 45000, "HR": 40000, "Finance": 50000, "Support": 32000}
e["salary"] = [int(b[x] + 2500 * y + rng.normal(0, 5000)) for x, y in zip(e.department, e.experience_years)]
e["performance_score"] = np.clip(rng.normal(70, 12, m), 30, 100).round(1)
e.loc[rng.choice(m, 4, replace=False), "salary"] *= 4
e.to_csv("sample_data/employees.csv", index=False)

s = 400
st = pd.DataFrame({"student_id": range(9001, 9001 + s), "gender": rng.choice(["Male", "Female"], s), "grade": rng.choice(["9th", "10th", "11th", "12th"], s)})
st["study_hours"] = np.clip(rng.normal(3, 1.4, s), 0, 8).round(1)
st["attendance"] = np.clip(rng.normal(82, 10, s), 40, 100).round(1)
for sub in ("math", "science", "english"):
    st[sub] = np.clip(30 + 8 * st.study_hours + .15 * st.attendance + rng.normal(0, 8, s), 0, 100).round(0).astype(int)
st["total_score"] = st.math + st.science + st.english
st.to_csv("sample_data/students.csv", index=False)
print("sample data generated")
