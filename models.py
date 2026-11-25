"""
models.py
SQLAlchemy models for the Momentum Dashboard app.
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, record):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


db = SQLAlchemy()


class Skill(db.Model):
    """A trackable skill/category, e.g. Python, Linux, English, Workout."""
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default="#0d6efd")  # hex color for charts/badges
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    weekly_target_minutes = db.Column(db.Integer, nullable=False, default=0)  # 0 = no goal

    activities = db.relationship(
        "Activity",
        backref="skill",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Activity.date.desc()",
    )

    def total_minutes(self):
        return sum(a.minutes for a in self.activities if not a.daily or not a.daily.deleted_at)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "total_minutes": self.total_minutes(),
            "activity_count": len(self.activities),
        }


class Activity(db.Model):
    """A single logged study/practice session for a skill on a given day."""
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    minutes = db.Column(db.Integer, nullable=False)
    quality = db.Column(db.Integer, nullable=False)       # 1-10
    completion = db.Column(db.Integer, nullable=False)    # 0-100 (%)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    daily = db.relationship('DailyTask', back_populates='activity', uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "skill_name": self.skill.name if self.skill else None,
            "skill_color": self.skill.color if self.skill else None,
            "date": self.date.isoformat(),
            "minutes": self.minutes,
            "quality": self.quality,
            "completion": self.completion,
            "notes": self.notes,
        }


PRIORITIES = ('Low', 'Medium', 'High', 'Urgent')
STATUSES = ('To Do', 'In Progress', 'On Hold', 'Completed')


class Task(db.Model):
    __tablename__ = 'tasks'
    __table_args__ = (
        db.CheckConstraint("status IN ('To Do','In Progress','On Hold','Completed')"),
        db.CheckConstraint("priority IN ('Low','Medium','High','Urgent')"),
        db.CheckConstraint('manual_progress >= 0 AND manual_progress <= 100'),
        db.CheckConstraint('due_date IS NULL OR start_date IS NULL OR due_date >= start_date'),
    )
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date, index=True)
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    status = db.Column(db.String(20), nullable=False, default='To Do', index=True)
    previous_status = db.Column(db.String(20), nullable=False, default='To Do')
    manual_progress = db.Column(db.Integer, nullable=False, default=0)
    deleted_at = db.Column(db.DateTime)
    # Legacy project_id remains in SQLite for data preservation only.
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='SET NULL'))
    category = db.relationship('Skill')
    subtasks = db.relationship('Subtask', cascade='all, delete-orphan', backref='task', order_by='Subtask.id')
    comments = db.relationship('Comment', cascade='all, delete-orphan', backref='task', order_by='Comment.created_at, Comment.id')
    logs = db.relationship('ActivityLog', cascade='all, delete-orphan', backref='task', order_by='ActivityLog.created_at, ActivityLog.id')
    daily_tasks = db.relationship('DailyTask', cascade='all, delete-orphan', backref='task', order_by='DailyTask.date, DailyTask.id')

    @property
    def progress(self):
        if self.status == 'Completed':
            return 100
        if self.subtasks:
            return round(sum(s.completed for s in self.subtasks) * 100 / len(self.subtasks))
        return self.manual_progress

    @property
    def overdue(self):
        return bool(self.due_date and self.due_date < date.today() and self.status != 'Completed' and not self.deleted_at)

    @property
    def due_soon(self):
        return bool(self.due_date and 0 <= (self.due_date - date.today()).days <= 3 and self.status != 'Completed')


class DailyTask(db.Model):
    """Date-only to-do, reusing the existing table without losing legacy data."""
    __tablename__ = 'calendar_events'
    __table_args__ = (
        db.CheckConstraint("priority IN ('Low','Medium','High','Urgent')"),
    )
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id', ondelete='SET NULL'), unique=True)
    activity = db.relationship('Activity', back_populates='daily', cascade='all, delete-orphan', single_parent=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='SET NULL'), index=True)
    skill = db.relationship('Skill')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    date = db.Column(db.Date, nullable=False, index=True)
    # Legacy time columns remain in SQLite, unused by the date-only application.
    notes = db.Column(db.Text, nullable=False, default='')
    priority = db.Column(db.String(10), nullable=False, default='Medium')
    completed = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Subtask(db.Model):
    __tablename__ = 'subtasks'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DailySkillSeed(db.Model):
    """Remember defaults already offered, even after a daily item is moved/deleted."""
    __tablename__ = 'daily_skill_seeds'
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id', ondelete='CASCADE'), primary_key=True)
    date = db.Column(db.Date, primary_key=True)
