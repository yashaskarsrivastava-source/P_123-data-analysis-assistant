# P_123 — Conversational Data Analysis Assistant

ChatGPT-style web app: upload CSV/XLSX, ask questions in English / Hindi / Hinglish, get **exact pandas results**, **ML insights** and an explanation whose numbers are **verified**.

## Architecture (hybrid engine)
UI → FastAPI → schema profiler → **operation router** (LLM planner *or* ML intent classifier) → pandas / scikit-learn execution → LLM explanation → **numeric validator** → table + chart

| Module | Role |
|---|---|
| `domain/data_analysis.py` | Pydantic plan/result models, allowed-operation enum |
| `engines/schema_profiler.py` | Load, validate, profile columns |
| `engines/router.py` | TF-IDF + Logistic Regression intent model + schema-aware entity extraction |
| `engines/operations.py` | Deterministic pandas ops + ML: Linear Regression forecast, Isolation Forest anomalies, KMeans clusters |
| `services/analysis_service.py` | Pipeline, LLM explanation, numeric validator, template fallback |

Safety: LLM never executes code. It only produces a JSON plan that is validated against the schema and the whitelist of 9 operations.

## Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000. Without SMTP configured, the generated password is shown on screen and printed in the terminal (dev mode).

## Run with Docker + PostgreSQL
```bash
cp .env.example .env     # fill SMTP + ANTHROPIC_API_KEY
docker compose up --build
```

## Tests
`cd backend && pytest` (count/average, filter/group, invalid column, unsupported operation, ML ops, Hindi).

## Try these
`total revenue by region where quantity > 5` · `top 3 products by revenue` · `forecast revenue` · `find outliers in revenue` · `segment the records into 4 clusters` · `salary ka ausat kitna hai` · `delete all rows` (rejected)

## Git workflow (per company handbook)
```bash
git checkout main && git pull origin main
git checkout <bhavesh|sathya|pallavi>
# copy the project in, then:
git status && git diff
git add . && git commit -m "Add conversational data analysis assistant with hybrid ML engine"
git push -u origin <your-branch>     # PR: base develop <- compare your branch
```
Never commit `.env` (already in `.gitignore`).
