"""
app.py
Momentum Dashboard - a Flask app for tracking daily skill-building activity.

Run with:
    python app.py
"""
import csv
import io
import os
import re
from datetime import date, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file
from sqlalchemy import func

from config import Config
from models import db, Skill, Activity
from activity_sync import activity_to_daily, visible_activity


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    # Make sure the instance folder exists for the SQLite file
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)

    with app.app_context():
        from migrate import upgrade
        upgrade()
        _seed_default_skills(app)

    register_routes(app)
    from planning import init_planning
    init_planning(app)

    @app.cli.command("upgrade-db")
    def upgrade_db():
        from migrate import upgrade
        upgrade()
        print("Database migrations are up to date.")

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
    return Activity.query.filter(visible_activity(), Activity.date >= start_date, Activity.date <= end_date)


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
        row[0] for row in db.session.query(Activity.date).filter(visible_activity()).distinct().all()
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
    ).filter(visible_activity()).scalar()
    total_hours = round((total_minutes or 0) / 60, 1)

    streak = calculate_streak()

    skills = Skill.query.filter_by(archived=False).order_by(Skill.name).all()
    recent_activities = (
        Activity.query.filter(visible_activity()).order_by(Activity.date.desc(), Activity.created_at.desc())
        .limit(8)
        .all()
    )

    # Weekly goals: current Saturday-Friday week (same week as the board).
    goal_week_start = today - timedelta(days=(today.weekday() - 5) % 7)
    goal_week_end = goal_week_start + timedelta(days=6)
    week_minutes = dict(
        db.session.query(Activity.skill_id, func.coalesce(func.sum(Activity.minutes), 0))
        .filter(visible_activity(), Activity.date.between(goal_week_start, goal_week_end))
        .group_by(Activity.skill_id)
        .all()
    )
    last_dates = dict(
        db.session.query(Activity.skill_id, func.max(Activity.date))
        .filter(visible_activity())
        .group_by(Activity.skill_id)
        .all()
    )
    skill_goals = []
    for skill in skills:
        done = int(week_minutes.get(skill.id, 0))
        target = skill.weekly_target_minutes or 0
        last = last_dates.get(skill.id)
        skill_goals.append({
            "skill": skill,
            "done_minutes": done,
            "target_minutes": target,
            "percent": min(100, round(done * 100 / target)) if target else None,
            "last_date": last,
            "days_since": (today - last).days if last else None,
            "stale": bool(last and (today - last).days >= 7),
        })

    return {
        "today": today_stats,
        "week": week_stats,
        "month": month_stats,
        "total_hours": total_hours,
        "streak": streak,
        "skills": skills,
        "skill_goals": skill_goals,
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
            .filter(visible_activity(), Activity.date == d)
            .scalar()
        )
        daily_minutes.append(int(total or 0))

    # Each stack has the skill's actual minutes, not a percentage or task count.
    skill_daily_rows = db.session.query(Activity.skill_id, Activity.date, func.sum(Activity.minutes)).filter(
        visible_activity(), Activity.date.between(days[0], days[-1])).group_by(Activity.skill_id, Activity.date).all()
    skill_minutes_by_day = {(sid, day): int(minutes) for sid, day, minutes in skill_daily_rows}
    week_skill_datasets = [dict(
        label=skill.name, skill_id=skill.id, backgroundColor=skill.color,
        data=[skill_minutes_by_day.get((skill.id, day), 0) for day in days]
    ) for skill in Skill.query.filter_by(archived=False).order_by(Skill.name).all()]

    # 2) Quality & completion trend for the last 14 days (single grouped query)
    trend_days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    trend_rows = db.session.query(
        Activity.date, func.avg(Activity.quality), func.avg(Activity.completion)
    ).filter(
        visible_activity(), Activity.date.between(trend_days[0], trend_days[-1])
    ).group_by(Activity.date).all()
    trend_by_day = {d: (q, c) for d, q, c in trend_rows}
    quality_trend = [round(trend_by_day[d][0], 1) if d in trend_by_day and trend_by_day[d][0] else None for d in trend_days]
    completion_trend = [round(trend_by_day[d][1], 1) if d in trend_by_day and trend_by_day[d][1] else None for d in trend_days]

    # 3) Total minutes distribution by skill (all-time, archived skills excluded)
    skill_rows = (
        db.session.query(Skill.name, Skill.color, func.coalesce(func.sum(Activity.minutes), 0))
        .outerjoin(Activity, (Activity.skill_id == Skill.id) & visible_activity())
        .filter(Skill.archived.is_(False))
        .group_by(Skill.id)
        .order_by(Skill.name)
        .all()
    )

    return {
        "week_labels": [d.strftime("%a %m/%d") for d in days],
        "week_minutes": daily_minutes,
        "week_skill_datasets": week_skill_datasets,
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
        from planning import weekly_context
        return render_template("planning/weekly.html", **weekly_context(), **get_dashboard_data())

    @app.route("/insights")
    def insights():
        return redirect(url_for("dashboard"))

    @app.route("/api/chart-data")
    def api_chart_data():
        return jsonify(get_chart_data())

    # ---------------------- Activities: List / CRUD ----------------------

    @app.route("/activities")
    def activities_list():
        skill_filter = request.args.get("skill_id", type=int)
        query = Activity.query.filter(visible_activity())
        if skill_filter:
            query = query.filter_by(skill_id=skill_filter)
        query = query.order_by(Activity.date.desc(), Activity.created_at.desc())
        page = request.args.get("page", 1, type=int) or 1
        pagination = query.paginate(page=page, per_page=25, error_out=False)
        skills = Skill.query.order_by(Skill.name).all()
        return render_template(
            "activities.html",
            activities=pagination.items,
            pagination=pagination,
            skills=skills,
            selected_skill_id=skill_filter,
        )

    @app.route("/export/activities.csv")
    def export_activities_csv():
        rows = (
            Activity.query.filter(visible_activity())
            .order_by(Activity.date, Activity.created_at)
            .all()
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "skill", "minutes", "quality", "completion", "notes"])
        for a in rows:
            writer.writerow([a.date.isoformat(), a.skill.name if a.skill else "",
                             a.minutes, a.quality, a.completion, a.notes or ""])
        filename = f"momentum-activities-{date.today().isoformat()}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.route("/export/database")
    def export_database():
        db_path = db.engine.url.database
        if not db_path or db_path == ":memory:" or not os.path.exists(db_path):
            flash("Database file is not available for export.", "danger")
            return redirect(url_for("dashboard"))
        filename = f"momentum-backup-{date.today().isoformat()}.db"
        return send_file(os.path.abspath(db_path), as_attachment=True, download_name=filename)

    @app.route("/activities/add", methods=["GET", "POST"])
    def activity_add():
        skills = Skill.query.filter_by(archived=False).order_by(Skill.name).all()
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
            activity_to_daily(activity)
            db.session.commit()
            flash("Activity logged successfully!", "success")
            return redirect(url_for("activities_list"))

        return render_template("add_activity.html", skills=skills, form=None, today=date.today().isoformat())

    @app.route("/activities/edit/<int:activity_id>", methods=["GET", "POST"])
    def activity_edit(activity_id):
        activity = Activity.query.get_or_404(activity_id)
        skills = Skill.query.filter(
            (Skill.archived.is_(False)) | (Skill.id == activity.skill_id)
        ).order_by(Skill.name).all()

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
            activity_to_daily(activity)
            db.session.commit()
            flash("Activity updated.", "success")
            return redirect(url_for("activities_list"))

        return render_template("edit_activity.html", activity=activity, skills=skills)

    @app.route("/activities/delete/<int:activity_id>", methods=["POST"])
    def activity_delete(activity_id):
        activity = Activity.query.get_or_404(activity_id)
        if activity.daily:
            db.session.delete(activity.daily)
        else:
            db.session.delete(activity)
        db.session.commit()
        flash("Activity deleted.", "info")
        return redirect(url_for("activities_list"))

    # ------------------------------ Skills --------------------------------

    @app.route("/skills")
    def skills_page():
        skills = Skill.query.filter_by(archived=False).order_by(Skill.name).all()
        archived_skills = Skill.query.filter_by(archived=True).order_by(Skill.name).all()
        return render_template("skills.html", skills=skills, archived_skills=archived_skills)

    @app.route("/skills/archive/<int:skill_id>", methods=["POST"])
    def skill_archive(skill_id):
        skill = Skill.query.get_or_404(skill_id)
        skill.archived = True
        db.session.commit()
        flash(f'Skill "{skill.name}" archived. Its history is kept.', "info")
        return redirect(url_for("skills_page"))

    @app.route("/skills/unarchive/<int:skill_id>", methods=["POST"])
    def skill_unarchive(skill_id):
        skill = Skill.query.get_or_404(skill_id)
        skill.archived = False
        db.session.commit()
        flash(f'Skill "{skill.name}" restored.', "success")
        return redirect(url_for("skills_page"))

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

    @app.route("/skills/edit/<int:skill_id>", methods=["GET", "POST"])
    def skill_edit(skill_id):
        skill = db.get_or_404(Skill, skill_id)
        error = None
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            color = request.form.get("color", "").strip()
            target_raw = request.form.get("weekly_target_minutes", "0").strip() or "0"
            try:
                target = int(target_raw)
                if target < 0 or target > 10080:
                    raise ValueError
            except ValueError:
                target = None
            if not name or len(name) > 50:
                error = "Name must contain 1–50 characters."
            elif not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                error = "Choose a valid color."
            elif target is None:
                error = "Weekly target must be a whole number of minutes between 0 and 10080 (0 = no goal)."
            elif Skill.query.filter(Skill.id != skill.id, func.lower(Skill.name) == name.lower()).first():
                error = "A skill with this name already exists."
            if error is None:
                from models import DailyTask
                DailyTask.query.filter_by(skill_id=skill.id, title=skill.name).update(
                    {DailyTask.title: name}, synchronize_session=False)
                skill.name, skill.color = name, color
                skill.weekly_target_minutes = target
                db.session.commit()
                flash("Skill updated.", "success")
                return redirect(url_for("skills_page"))
        return render_template("edit_skill.html", skill=skill, error=error,
                               form=request.form if request.method == "POST" else {}), 400 if error else 200

    @app.route("/skills/delete/<int:skill_id>", methods=["POST"])
    def skill_delete(skill_id):
        skill = Skill.query.get_or_404(skill_id)
        activity_count = Activity.query.filter_by(skill_id=skill.id).count()
        if activity_count:
            flash(
                f'Skill "{skill.name}" has {activity_count} logged activities and cannot be deleted. '
                "Archive it instead to hide it without losing history.",
                "danger",
            )
            return redirect(url_for("skills_page"))
        db.session.delete(skill)
        db.session.commit()
        flash(f'Skill "{skill.name}" was deleted.', "info")
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
    # Local-only by default. Set FLASK_DEBUG=1 only for development on your own machine.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
