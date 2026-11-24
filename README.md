# AI Bias Detector (no-install version)

Upload a CSV of decisions (loans, hiring, admissions) and get a fairness audit.
Python backend (standard library only) + SQLite history + website served by the same server.
No pip, no virtual environment, no Node: only Python 3.9+.

## Run
```
cd backend
python server.py
```
Open http://localhost:8000. Stop with Ctrl + C.

## Test
```
cd backend
python -m unittest discover tests
```

## How the score works
For each attribute, groups are compared on the rate of the favourable outcome.
Disparity ratio = lowest group rate / highest group rate. Bias score = round((1 - ratio) x 100).
A ratio under 0.80 fails the four-fifths rule. Groups under 5 rows are ignored.
This shows statistical disparity, not its cause, and is not legal advice.

## Files
- backend/audit_lite.py - the maths (detection, grouping, ratio, score, sample data)
- backend/server.py - API routes, SQLite history, serves the website
- backend/tests/ - unit tests
- frontend/index.html - the website (Home, Upload, Results, History)

## Deploy (Render, free)
1. Put this folder on GitHub (repository root = this folder).
2. render.com > New > Web Service (or Blueprint) > pick the repo.
3. Runtime Python, Build command `echo ok`, Start command `python backend/server.py`.
4. Deploy. Your site is at https://<name>.onrender.com
Notes: free instances sleep after ~15 min idle (first load is slow) and audit history is wiped on
restart/redeploy. History is private per browser (random id stored in localStorage).
