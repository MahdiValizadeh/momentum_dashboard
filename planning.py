"""Persistent weekly to-dos and independent long-term tasks."""
from datetime import date, datetime, timedelta
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, session, current_app
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy import or_
from activity_sync import sync_daily_activity
from models import Activity
from models import db, Task, DailyTask, DailySkillSeed, Subtask, Comment, ActivityLog, Skill, PRIORITIES, STATUSES

bp = Blueprint('planning', __name__)


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(32)
    return session['_csrf']


def init_planning(app):
    app.register_blueprint(bp)
    app.jinja_env.globals.update(csrf_token=csrf_token, priorities=PRIORITIES, statuses=STATUSES)

    @app.before_request
    def protect_forms():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            expected = session.get('_csrf')
            if not expected or not secrets.compare_digest(str(token), expected):
                abort(400, description='This form expired. Reload the page and try again.')

    @app.errorhandler(400)
    def bad_request(error):
        if wants_json():
            return jsonify(error=error.description), 400
        return render_template('planning/error.html', error=error.description), 400


@bp.app_context_processor
def choices():
    return {'today_date': date.today()}


def log(task, message):
    db.session.add(ActivityLog(task=task, message=message))


def required_text(form, key, maximum=200):
    value = form.get(key, '')
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{key.replace("_", " ").title()} is required (maximum {maximum} characters).')
    return value.strip()


def optional_text(form, key, maximum=20000):
    value = form.get(key, '')
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{key.title()} is too long.')
    return value.strip()


def parse_date(value, required=False):
    if not value and not required:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Please enter a valid date.')


def relation(form, key, cls):
    raw = form.get(key)
    if not raw:
        return None
    try:
        obj = db.session.get(cls, int(raw))
    except (ValueError, TypeError):
        obj = None
    if obj is None:
        raise ValueError(f'Invalid {key.replace("_id", "")}.')
    return obj.id


def enum(form, key, values, default):
    value = form.get(key, default)
    if value not in values:
        raise ValueError(f'Invalid {key}.')
    return value


def change_status(task, status):
    if status != task.status:
        old = task.status
        if status == 'Completed':
            task.previous_status = old
        task.status = status
        log(task, f'Status: {old} → {status}')


def active_task(task_id):
    task = db.get_or_404(Task, task_id)
    if task.deleted_at:
        abort(400, description='Restore this task before editing it.')
    return task


def visible_daily_tasks():
    return DailyTask.query.outerjoin(Task).filter(
        DailyTask.deleted_at.is_(None),
        or_(DailyTask.task_id.is_(None), (Task.deleted_at.is_(None) & (Task.status != 'Completed'))))


def ensure_skill_defaults(days):
    if not current_app.config.get('AUTO_DAILY_SKILLS', True):
        return
    for skill in Skill.query.filter_by(archived=False).order_by(Skill.id).all():
        for day in days:
            result = db.session.execute(insert(DailySkillSeed).values(
                skill_id=skill.id, date=day).on_conflict_do_nothing())
            if result.rowcount:
                db.session.add(DailyTask(title=skill.name, date=day, skill_id=skill.id))
    db.session.commit()


def weekly_context():
    try:
        anchor = parse_date(request.args.get('week')) or date.today()
        start = anchor - timedelta(days=(anchor.weekday() - 5) % 7)
        days = [start + timedelta(days=i) for i in range(7)]
        prev, nxt = start - timedelta(days=7), start + timedelta(days=7)
    except (ValueError, OverflowError):
        abort(400, description='Invalid week.')
    ensure_skill_defaults(days)
    items = visible_daily_tasks().filter(DailyTask.date.between(days[0], days[-1])).order_by(DailyTask.completed.desc(), DailyTask.id).all()
    active = Task.query.filter(Task.deleted_at.is_(None), Task.status != 'Completed')
    return dict(days=days, by_day={d: [item for item in items if item.date == d] for d in days},
                prev=prev, nxt=nxt, week_start=start,
                completed_count=sum(item.completed for item in items),
                remaining_count=sum(not item.completed for item in items),
                active_count=active.count(), overdue_count=active.filter(Task.due_date < date.today()).count(),
                active_tasks=active.order_by(Task.due_date.is_(None), Task.due_date, Task.id).limit(3).all())


@bp.route('/tasks')
def tasks():
    status = request.args.get('status', 'Active')
    if status not in ('Active', 'All', 'Archived') + STATUSES:
        abort(400, description='Invalid task filter.')
    query = Task.query
    if status == 'Archived': query = query.filter(Task.deleted_at.is_not(None))
    else:
        query = query.filter(Task.deleted_at.is_(None))
        if status == 'Active': query = query.filter(Task.status != 'Completed')
        elif status != 'All': query = query.filter_by(status=status)
    search = request.args.get('q', '').strip()[:200]
    if search: query = query.filter(Task.title.contains(search, autoescape=True))
    return render_template('planning/tasks.html', tasks=query.order_by(Task.due_date.is_(None), Task.due_date, Task.id.desc()).all(), selected=status,
                           search=search)


def task_fields(form):
    start, due = parse_date(form.get('start_date')), parse_date(form.get('due_date'))
    if start and due and due < start: raise ValueError('Due date must be on or after the start date.')
    try: progress = int(form.get('manual_progress', '0'))
    except (ValueError, TypeError): raise ValueError('Progress must be a whole number from 0 to 100.')
    if not 0 <= progress <= 100: raise ValueError('Progress must be from 0 to 100.')
    return dict(title=required_text(form, 'title'), description=optional_text(form, 'description'), start_date=start, due_date=due,
                priority=enum(form, 'priority', PRIORITIES, 'Medium'), status=enum(form, 'status', STATUSES, 'To Do'),
                manual_progress=progress, skill_id=relation(form, 'skill_id', Skill))


@bp.route('/tasks/new', methods=['GET', 'POST'])
@bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
def task_form(task_id=None):
    task = active_task(task_id) if task_id else None
    code = 200
    if request.method == 'POST':
        try:
            fields = task_fields(request.form)
            status = fields.pop('status')
            if task is None:
                task = Task(**fields, status='To Do', previous_status='To Do')
                db.session.add(task)
                log(task, 'Task created')
            else:
                for key, value in fields.items():
                    old = getattr(task, key)
                    if old != value:
                        log(task, f'{key.replace("_", " ").title()}: {old if old is not None else "—"} → {value if value is not None else "—"}')
                        setattr(task, key, value)
            change_status(task, status)
            db.session.commit()
            return redirect(url_for('planning.task_detail', task_id=task.id))
        except ValueError as exc:
            flash(str(exc), 'danger')
            code = 400
    return render_template('planning/task_form.html', task=task, form=request.form if request.method == 'POST' else None,
                           skills=Skill.query.order_by(Skill.name).all()), code


@bp.route('/tasks/<int:task_id>')
def task_detail(task_id):
    return render_template('planning/task_detail.html', task=db.get_or_404(Task, task_id))


@bp.route('/tasks/<int:task_id>/delete', methods=['GET', 'POST'])
def task_delete(task_id):
    task = db.get_or_404(Task, task_id)
    if request.method == 'POST':
        if request.form.get('confirm') != 'delete':
            abort(400, description='Confirm permanent deletion first.')
        db.session.delete(task)
        db.session.commit()
        flash('Task and all its comments, checklist, history and linked daily tasks permanently deleted.', 'info')
        return redirect(url_for('planning.tasks'))
    return render_template('planning/task_delete.html', task=task)


@bp.post('/tasks/<int:task_id>/action')
def task_action(task_id):
    task = db.get_or_404(Task, task_id)
    action = request.form.get('action')
    if action == 'restore':
        task.deleted_at = None
        log(task, 'Task restored')
    elif action == 'archive':
        task.deleted_at = datetime.utcnow()
        log(task, 'Task archived; history retained')
    else:
        if task.deleted_at: abort(400, description='Restore this task first.')
        if action == 'reopen':
            if task.status == 'Completed':
                change_status(task, task.previous_status if task.previous_status in STATUSES[:-1] else 'To Do')
        elif action == 'status':
            try: change_status(task, enum(request.form, 'status', STATUSES, 'To Do'))
            except ValueError as exc: abort(400, description=str(exc))
        else: abort(400, description='Unknown action.')
    db.session.commit()
    return redirect(url_for('planning.task_detail', task_id=task.id))


@bp.post('/tasks/<int:task_id>/subtasks')
def subtask_add(task_id):
    task = active_task(task_id)
    try: title = required_text(request.form, 'title')
    except ValueError as exc: abort(400, description=str(exc))
    db.session.add(Subtask(task=task, title=title))
    log(task, f'Subtask added: {title}')
    db.session.commit()
    return redirect(url_for('planning.task_detail', task_id=task.id))


@bp.post('/subtasks/<int:subtask_id>')
def subtask_update(subtask_id):
    sub = db.get_or_404(Subtask, subtask_id)
    task = active_task(sub.task_id)
    action = request.form.get('action')
    if action == 'toggle':
        sub.completed = not sub.completed
        log(task, f'Subtask {"completed" if sub.completed else "reopened"}: {sub.title}')
    elif action == 'delete':
        log(task, f'Subtask removed: {sub.title}')
        db.session.delete(sub)
    elif action == 'edit':
        try: title = required_text(request.form, 'title')
        except ValueError as exc: abort(400, description=str(exc))
        log(task, f'Subtask renamed: {sub.title} → {title}')
        sub.title = title
    else: abort(400, description='Unknown subtask action.')
    db.session.commit()
    return redirect(url_for('planning.task_detail', task_id=task.id))


@bp.post('/tasks/<int:task_id>/comments')
def comment_add(task_id):
    task = active_task(task_id)
    try: body = required_text(request.form, 'body', 20000)
    except ValueError as exc: abort(400, description=str(exc))
    db.session.add(Comment(task=task, body=body))
    log(task, 'Comment added')
    db.session.commit()
    return redirect(url_for('planning.task_detail', task_id=task.id))


@bp.post('/comments/<int:comment_id>')
def comment_update(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    task = active_task(comment.task_id)
    action = request.form.get('action')
    if action == 'delete':
        db.session.delete(comment)
        log(task, 'Comment deleted')
    elif action == 'edit':
        try: comment.body = required_text(request.form, 'body', 20000)
        except ValueError as exc: abort(400, description=str(exc))
        comment.updated_at = datetime.utcnow()
        log(task, 'Comment edited')
    else: abort(400, description='Unknown comment action.')
    db.session.commit()
    return redirect(url_for('planning.task_detail', task_id=task.id))


def daily_fields(form, existing=None):
    task_id = relation(form, 'task_id', Task)
    if task_id:
        task = db.session.get(Task, task_id)
        if (task.deleted_at or task.status == 'Completed') and not (existing and existing.task_id == task_id):
            raise ValueError('Choose an active task, or reopen the task first.')
    return dict(title=required_text(form, 'title'), description=optional_text(form, 'description'),
                notes=optional_text(form, 'notes'), date=parse_date(form.get('date'), True),
                priority=enum(form, 'priority', PRIORITIES, 'Medium'), task_id=task_id)


def wants_json():
    return request.is_json or request.headers.get('Accept') == 'application/json'


@bp.post('/daily-tasks/quick-add')
def daily_quick_add():
    try:
        item = DailyTask(title=required_text(request.form, 'title'), date=parse_date(request.form.get('date'), True))
    except ValueError as exc:
        abort(400, description=str(exc))
    db.session.add(item)
    db.session.commit()
    if wants_json():
        return jsonify(id=item.id, html=render_template('planning/daily_row.html', item=item)), 201
    return redirect(url_for('dashboard', week=item.date.isoformat(), _anchor='day-' + item.date.isoformat()))


# Existing event URLs remain aliases so saved links still reach the same data.
@bp.route('/events/new', methods=['GET', 'POST'])
@bp.route('/events/<int:item_id>/edit', methods=['GET', 'POST'])
@bp.route('/daily-tasks/new', methods=['GET', 'POST'])
@bp.route('/daily-tasks/<int:item_id>/edit', methods=['GET', 'POST'])
def daily_form(item_id=None):
    item = db.get_or_404(DailyTask, item_id) if item_id else None
    if item and item.deleted_at: abort(404)
    code = 200
    if request.method == 'POST':
        try:
            fields = daily_fields(request.form, item)
            activity_values = None
            if 'minutes' in request.form and (request.form.get('minutes', '').strip() or (item and item.activity)):
                skill_id = relation(request.form, 'skill_id', Skill)
                if not skill_id: raise ValueError('Select a skill to record activity time.')
                try:
                    minutes = int(request.form.get('minutes', ''))
                    quality = int(request.form.get('quality', '7'))
                    completion = int(request.form.get('completion', '100'))
                except (ValueError, TypeError): raise ValueError('Minutes, quality and completion must be whole numbers.')
                if not 1 <= minutes <= 1440 or not 1 <= quality <= 10 or not 0 <= completion <= 100:
                    raise ValueError('Minutes: 1–1440, quality: 1–10, completion: 0–100.')
                activity_values = dict(skill_id=skill_id, minutes=minutes, quality=quality,
                                       completion=completion, notes=fields['notes'], date=fields['date'])
            old_task = item.task if item else None
            if item is None:
                item = DailyTask(**fields)
                db.session.add(item)
                message = 'Daily task created: ' + item.title
            else:
                changes = [f'{k}: {getattr(item, k)} → {v}' for k, v in fields.items() if getattr(item, k) != v]
                for k, v in fields.items(): setattr(item, k, v)
                message = 'Daily task updated: ' + '; '.join(changes)
            if activity_values:
                if item.activity is None: item.activity = Activity(**activity_values)
                else:
                    for key, value in activity_values.items(): setattr(item.activity, key, value)
                item.skill_id = activity_values['skill_id']
                item.completed = activity_values['completion'] == 100
            sync_daily_activity(item)
            target = db.session.get(Task, fields['task_id']) if fields['task_id'] else None
            if old_task and old_task != target: log(old_task, 'Daily task unlinked: ' + item.title)
            if target: log(target, message)
            db.session.commit()
            return redirect(url_for('planning.daily_detail', item_id=item.id))
        except ValueError as exc:
            flash(str(exc), 'danger')
            code = 400
    form = request.form if request.method == 'POST' else (request.args if item is None else None)
    task_choices = Task.query.filter(Task.deleted_at.is_(None), Task.status != 'Completed').order_by(Task.title).all()
    if item and item.task and item.task not in task_choices:
        task_choices.append(item.task)
    return render_template('planning/daily_form.html', item=item, form=form, task_choices=task_choices, skills=Skill.query.order_by(Skill.name).all()), code


@bp.route('/events/<int:item_id>')
@bp.route('/daily-tasks/<int:item_id>')
def daily_detail(item_id):
    return render_template('planning/daily_detail.html', item=db.get_or_404(DailyTask, item_id))


@bp.post('/events/<int:item_id>/action')
@bp.post('/daily-tasks/<int:item_id>/action')
def daily_action(item_id):
    item = db.get_or_404(DailyTask, item_id)
    action = request.form.get('action')
    if action == 'delete': item.deleted_at = datetime.utcnow()
    elif action == 'restore': item.deleted_at = None
    elif action == 'toggle' and not item.deleted_at:
        completed = request.form.get('completed')
        if completed not in (None, '0', '1'): abort(400, description='Invalid completion value.')
        item.completed = not item.completed if completed is None else completed == '1'
        if item.activity: item.activity.completion = 100 if item.completed else 0
    else: abort(400, description='Invalid daily task action.')
    if item.task: log(item.task, f'Daily task {action}: {item.title}')
    db.session.commit()
    if wants_json():
        return jsonify(id=item.id, completed=item.completed, deleted=bool(item.deleted_at), has_activity=bool(item.activity_id))
    if action == 'delete':
        flash('Daily task deleted. You can restore it from its details page.', 'info')
        return redirect(url_for('planning.daily_detail', item_id=item.id))
    if request.form.get('return_to') == 'detail':
        return redirect(url_for('planning.daily_detail', item_id=item.id))
    return redirect(url_for('dashboard', week=item.date.isoformat(), _anchor='day-' + item.date.isoformat()))


@bp.post('/api/events/<int:item_id>/move')
@bp.post('/api/daily-tasks/<int:item_id>/move')
def daily_move(item_id):
    item = db.get_or_404(DailyTask, item_id)
    if item.deleted_at or (item.task and (item.task.deleted_at or item.task.status == 'Completed')):
        abort(400, description='Only active daily tasks can be moved.')
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict): abort(400, description='Expected a JSON object.')
    try: new_date = parse_date(payload.get('date'), True)
    except ValueError as exc: abort(400, description=str(exc))
    old = item.date
    item.date = new_date
    sync_daily_activity(item)
    if item.task: log(item.task, f'Daily task moved: {item.title}: {old} → {new_date}')
    db.session.commit()
    return jsonify(id=item.id, date=item.date.isoformat())
