# 📈 Momentum Dashboard

A self-hosted Flask web app for tracking daily progress on the skills you're
building — Python, Linux, English, Workout, or anything else you add.

Log a session, rate its quality and completion, and watch your streak,
weekly/monthly totals, and trends update automatically on a Bootstrap 5 +
Chart.js dashboard.

---

## ✨ Features

- **Daily activity logging** — skill, minutes, quality (1–10), completion (%), notes
- **Dynamic skills** — add/remove your own skills at any time (Python, Linux, English, Workout ship as defaults)
- **Dashboard at a glance**
  - Today's progress
  - Weekly progress (last 7 days)
  - Monthly progress (calendar month)
  - Current streak (consecutive days logged)
  - Total study hours (all-time)
- **Full CRUD** for both activities and skills
- **Interactive charts** (Chart.js): minutes per day, skill time distribution, quality/completion trend
- **SQLite** storage — zero external services, single file database
- **Clean project structure**, ready to run locally in minutes

---

## 🗂 Project Structure

```
momentum_dashboard/
├── app.py                  # Flask app factory, routes, dashboard/stat logic
├── config.py                # App configuration (DB URI, default skills)
├── models.py                 # SQLAlchemy models: Skill, Activity
├── requirements.txt
├── README.md
├── .gitignore
├── instance/                 # SQLite DB file lives here (auto-created)
├── static/
│   ├── css/style.css         # Custom dashboard styling
│   └── js/charts.js          # Chart.js rendering, fetches /api/chart-data
└── templates/
    ├── base.html             # Shared layout, navbar
    ├── index.html            # Dashboard page
    ├── activities.html       # Activity list + filters
    ├── add_activity.html     # Create activity form
    ├── edit_activity.html    # Edit activity form
    ├── skills.html           # Skill management
    └── 404.html
```

---

## 🚀 Getting Started

### 1. Clone / unzip the project and enter the folder
```bash
cd momentum_dashboard
```

### 2. Create a virtual environment (recommended)
```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python app.py
```

The app starts on **http://127.0.0.1:5000** and automatically:
- creates the `instance/momentum.db` SQLite database on first run
- seeds it with 4 default skills: Python, Linux, English, Workout

Open the URL in your browser and start logging activity 🎉

---

## 🧭 Usage Guide

| Action | Where |
|---|---|
| View dashboard stats & charts | `/` |
| Log a new activity | `/activities/add` (or the "Log Activity" button) |
| View / filter / edit / delete activities | `/activities` |
| Add or remove a skill | `/skills` |

**Streak logic:** a day counts toward your streak if at least one activity
was logged on it. The streak counts consecutive days ending today; if you
haven't logged anything yet today, yesterday's streak stays "alive" until
midnight so you don't lose it while your day is still in progress.

**Deleting a skill** also deletes all activities logged under it (cascade
delete) — you'll be asked to confirm this in the UI.

---

## 🛠 Tech Stack

- **Backend:** Python 3, Flask
- **Database:** SQLite via Flask-SQLAlchemy (ORM)
- **Frontend:** Bootstrap 5, Bootstrap Icons
- **Charts:** Chart.js (loaded from CDN)
- **Templating:** Jinja2

---

## 🔧 Configuration

Environment variables (optional, all have sensible defaults):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session secret | `dev-secret-key-change-in-production` |
| `DATABASE_URL` | SQLAlchemy DB URI | `sqlite:///instance/momentum.db` |

For production, set a strong `SECRET_KEY` and run behind a proper WSGI
server (e.g. `gunicorn app:app`) instead of the Flask dev server.

---

## 📊 API

The dashboard charts are powered by a small JSON endpoint you can reuse:

```
GET /api/chart-data
```

Returns 7-day minute totals, 14-day quality/completion trends, and
all-time minutes distribution by skill.

---

## 📄 License

Free to use and modify for personal or educational purposes.
