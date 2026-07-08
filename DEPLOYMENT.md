# Deploying WeGo — get it live on the internet (free, ~5 minutes)

This app is tested and working (signup → guide profile → search → booking →
accept/reject → complete → review, all confirmed end-to-end). It's now set
up to run in production with `gunicorn` instead of Flask's dev server, and
reads its secret key / port from environment variables — the only two things
a real host needs.

I can't push this to a hosting account myself (I have no internet access and
no login to your accounts), but here's exactly what to do. **Render** is the
easiest free option and doesn't require a credit card for this tier.

## Option A: Render (recommended)

1. **Put this folder in a GitHub repo.**
   - Go to github.com → New repository → name it `wego` → create it.
   - Upload these files: `main.py`, `requirements.txt`, `Procfile`, `.gitignore`
     (drag-and-drop works fine on github.com, no git command line needed).

2. **Create the Render service.**
   - Go to [render.com](https://render.com) → sign up (GitHub login is easiest).
   - Dashboard → **New +** → **Web Service**.
   - Connect your GitHub account, select the `wego` repo.
   - Settings:
     - **Runtime:** Python 3
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `gunicorn main:app --bind 0.0.0.0:$PORT`
     - **Instance Type:** Free
   - Under **Environment**, add a variable:
     - Key: `SECRET_KEY`  Value: any long random string (e.g. mash your keyboard)
   - Click **Create Web Service**.

3. **Wait ~2 minutes** for the build. Render gives you a live URL like
   `https://wego-xxxx.onrender.com` — that's your app, live for anyone.

**One thing to know:** the free tier uses SQLite stored on disk, which Render
wipes on redeploys/restarts on the free plan. That's fine for a portfolio demo
and for the "get 3–5 people to test it" feedback round from the README. If
you later want data to persist permanently, swap SQLite for Render's free
PostgreSQL add-on — worth doing once you're past the feedback stage, not before.

## Option B: Railway (alternative, similar steps)

Same idea: push to GitHub, sign up at [railway.app](https://railway.app), New
Project → Deploy from GitHub repo → it auto-detects Python and the `Procfile`.
Add `SECRET_KEY` under Variables. Railway's free tier has usage-based limits
(a few dollars of monthly credit) rather than Render's always-free tier.

## Running it locally first (optional sanity check)

```bash
pip install -r requirements.txt
python3 main.py
```
Then open `http://127.0.0.1:5000` in a browser. This uses Flask's dev server
(fine for local testing) — production uses gunicorn via the Procfile instead.

## What's next (per the Blueprint)

Once this is live and you've gathered feedback, the
`WeGo-Guide-Marketplace-Blueprint.md` phase plan (React frontend + FastAPI +
PostgreSQL) is the natural next step — but this working Flask version is a
complete, demoable product on its own first.
