"""
app.py
Momentum Dashboard - a Flask app for tracking daily skill-building activity.

Run with:
    python app.py
"""
import os
from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func

from config import Config
from models import db, Skill, Activity


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Make sure the instance folder exists for the SQLite file
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_default_skills(app)

    register_routes(app)
    return app


def _seed_default_skills(app):
    """Populate the skills table with sane defaults on first run."""
    if Skill.query.count() == 0:
        for s in app.config["DEFAULT_SKILLS"]:
            db.session.add(Skill(name=s["name"], color=s["color"]))
        db.session.commit()


# --------------------------------------------------------------------------
# Stat / aggregation helpers
# --------------------------------------------------------------------------

def _activities_between(start_date, end_date):
    """Inclusive range query."""
    return Activity.query.filter(Activity.date >= start_date, Activity.date <= end_date)


def get_period_stats(start_date, end_date):
    """Aggregate minutes / avg quality / avg completion / session count for a date range."""
    q = _activities_between(start_date, end_date)
    total_minutes = q.with_entities(func.coalesce(func.sum(Activity.minutes), 0)).scalar()
    avg_quality = q.with_entities(func.avg(Activity.quality)).scalar()
    avg_completion = q.with_entities(func.avg(Activity.completion)).scalar()
    count = q.count()
    return {
        "minutes": int(total_minutes or 0),
        "hours": round((total_minutes or 0) / 60, 1),
        "avg_quality": round(avg_quality, 1) if avg_quality else 0,
        "avg_completion": round(avg_completion, 1) if avg_completion else 0,
        "sessions": count,
    }


def calculate_streak():
    """
    Current streak = number of consecutive days (ending today or yesterday)
    that have at least one logged activity.
    Grace: if nothing has been logged *yet today*, the streak still counts
    as alive as long as yesterday was logged.
    """
    active_dates = {
        row[0] for row in db.session.query(Activity.date).distinct().all()
    }
    if not active_dates:
        return 0

    today = date.today()
    cursor = today if today in active_dates else today - timedelta(days=1)

    streak = 0
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_dashboard_data():
    today = date.today()
    week_start = today - timedelta(days=6)  # last 7 days incl. today
    month_start = today.replace(day=1)

    today_stats = get_period_stats(today, today)
    week_stats = get_period_stats(week_start, today)
    month_stats = get_period_stats(month_start, today)

    total_minutes = db.session.query(
        func.coalesce(func.sum(Activity.minutes), 0)
    ).scalar()
    total_hours = round((total_minutes or 0) / 60, 1)

    streak = calculate_streak()

    skills = Skill.query.order_by(Skill.name).all()
    recent_activities = (
        Activity.query.order_by(Activity.date.desc(), Activity.created_at.desc())
        .limit(8)
        .all()
    )

    return {
        "today": today_stats,
        "week": week_stats,
        "month": month_stats,
        "total_hours": total_hours,
        "streak": streak,
        "skills": skills,
        "recent_activities": recent_activities,
    }


def get_chart_data():
    """Build JSON-serializable data for the Chart.js charts on the dashboard."""
    today = date.today()

    # 1) Minutes per day for the last 7 days
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_minutes = []
    for d in days:
        total = (
            db.session.query(func.coalesce(func.sum(Activity.minutes), 0))
            .filter(Activity.date == d)
            .scalar()
        )
        daily_minutes.append(int(total or 0))

    # 2) Quality & completion trend for the last 14 days
    trend_days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    quality_trend = []
    completion_trend = []
    for d in trend_days:
        q = (
            db.session.query(func.avg(Activity.quality))
            .filter(Activity.date == d)
            .scalar()
        )
        c = (
            db.session.query(func.avg(Activity.completion))
            .filter(Activity.date == d)
            .scalar()
        )
        quality_trend.append(round(q, 1) if q else None)
        completion_trend.append(round(c, 1) if c else None)

    # 3) Total minutes distribution by skill (all-time)
    skill_rows = (
        db.session.query(Skill.name, Skill.color, func.coalesce(func.sum(Activity.minutes), 0))
        .outerjoin(Activity, Activity.skill_id == Skill.id)
        .group_by(Skill.id)
        .order_by(Skill.name)
        .all()
    )

    return {
        "week_labels": [d.strftime("%a %m/%d") for d in days],
        "week_minutes": daily_minutes,
        "trend_labels": [d.strftime("%m/%d") for d in trend_days],
        "quality_trend": quality_trend,
        "completion_trend": completion_trend,
        "skill_names": [r[0] for r in skill_rows],
        "skill_colors": [r[1] for r in skill_rows],
        "skill_minutes": [int(r[2]) for r in skill_rows],
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

def register_routes(app):

    @app.route("/")
    def dashboard():
        data = get_dashboard_data()
        return render_template("index.html", **data)

    @app.route("/api/chart-data")
    def api_chart_data():
        return jsonify(get_chart_data())

    # ---------------------- Activities: List / CRUD ----------------------

    @app.route("/activities")
    def activities_list():
        skill_filter = request.args.get("skill_id", type=int)
        query = Activity.query
        if skill_filter:
            query = query.filter_by(skill_id=skill_filter)
        activities = query.order_by(Activity.date.desc(), Activity.created_at.desc()).all()
        skills = Skill.query.order_by(Skill.name).all()
        return render_template(
            "activities.html",
            activities=activities,
            skills=skills,
            selected_skill_id=skill_filter,
        )

    @app.route("/activities/add", methods=["GET", "POST"])
    def activity_add():
        skills = Skill.query.order_by(Skill.name).all()
        if not skills:
            flash("Please create a skill first.", "warning")
            return redirect(url_for("skills_page"))

        if request.method == "POST":
            error = _validate_activity_form(request.form)
            if error:
                flash(error, "danger")
                return render_template("add_activity.html", skills=skills, form=request.form, today=date.today().isoformat())

            activity = Activity(
                skill_id=int(request.form["skill_id"]),
                date=date.fromisoformat(request.form["date"]),
                minutes=int(request.form["minutes"]),
                quality=int(request.form["quality"]),
                completion=int(request.form["completion"]),
                notes=request.form.get("notes", "").strip(),
            )
            db.session.add(activity)
            db.session.commit()
            flash("Activity logged successfully!", "success")
            return redirect(url_for("activities_list"))

        return render_template("add_activity.html", skills=skills, form=None, today=date.today().isoformat())

    @app.route("/activities/edit/<int:activity_id>", methods=["GET", "POST"])
    def activity_edit(activity_id):
        activity = Activity.query.get_or_404(activity_id)
        skills = Skill.query.order_by(Skill.name).all()

        if request.method == "POST":
            error = _validate_activity_form(request.form)
            if error:
                flash(error, "danger")
                return render_template("edit_activity.html", activity=activity, skills=skills)

            activity.skill_id = int(request.form["skill_id"])
            activity.date = date.fromisoformat(request.form["date"])
            activity.minutes = int(request.form["minutes"])
            activity.quality = int(request.form["quality"])
            activity.completion = int(request.form["completion"])
            activity.notes = request.form.get("notes", "").strip()
            db.session.commit()
            flash("Activity updated.", "success")
            return redirect(url_for("activities_list"))

        return render_template("edit_activity.html", activity=activity, skills=skills)

    @app.route("/activities/delete/<int:activity_id>", methods=["POST"])
    def activity_delete(activity_id):
        activity = Activity.query.get_or_404(activity_id)
        db.session.delete(activity)
        db.session.commit()
        flash("Activity deleted.", "info")
        return redirect(url_for("activities_list"))

    # ------------------------------ Skills --------------------------------

    @app.route("/skills")
    def skills_page():
        skills = Skill.query.order_by(Skill.name).all()
        return render_template("skills.html", skills=skills)

    @app.route("/skills/add", methods=["POST"])
    def skill_add():
        name = request.form.get("name", "").strip()
        color = request.form.get("color", "#0d6efd").strip() or "#0d6efd"

        if not name:
            flash("Skill name is required.", "danger")
        elif Skill.query.filter(func.lower(Skill.name) == name.lower()).first():
            flash(f'Skill "{name}" already exists.', "warning")
        else:
            db.session.add(Skill(name=name, color=color))
            db.session.commit()
            flash(f'Skill "{name}" added.', "success")
        return redirect(url_for("skills_page"))

    @app.route("/skills/delete/<int:skill_id>", methods=["POST"])
    def skill_delete(skill_id):
        skill = Skill.query.get_or_404(skill_id)
        db.session.delete(skill)  # cascades to its activities
        db.session.commit()
        flash(f'Skill "{skill.name}" and its activities were deleted.', "info")
        return redirect(url_for("skills_page"))

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404


def _validate_activity_form(form):
    """Return an error message string, or None if the form is valid."""
    try:
        skill_id = int(form.get("skill_id", ""))
        if not Skill.query.get(skill_id):
            return "Please select a valid skill."
    except (TypeError, ValueError):
        return "Please select a valid skill."

    try:
        date.fromisoformat(form.get("date", ""))
    except ValueError:
        return "Please provide a valid date."

    try:
        minutes = int(form.get("minutes", ""))
        if minutes <= 0 or minutes > 1440:
            return "Minutes must be between 1 and 1440."
    except (TypeError, ValueError):
        return "Minutes must be a whole number."

    try:
        quality = int(form.get("quality", ""))
        if not (1 <= quality <= 10):
            return "Quality must be between 1 and 10."
    except (TypeError, ValueError):
        return "Quality must be a whole number between 1 and 10."

    try:
        completion = int(form.get("completion", ""))
        if not (0 <= completion <= 100):
            return "Completion must be between 0 and 100."
    except (TypeError, ValueError):
        return "Completion must be a whole number between 0 and 100."

    return None


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
