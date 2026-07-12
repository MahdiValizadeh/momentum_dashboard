"""
models.py
SQLAlchemy models for the Momentum Dashboard app.
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Skill(db.Model):
    """A trackable skill/category, e.g. Python, Linux, English, Workout."""
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default="#0d6efd")  # hex color for charts/badges
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    activities = db.relationship(
        "Activity",
        backref="skill",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Activity.date.desc()",
    )

    def total_minutes(self):
        return sum(a.minutes for a in self.activities)

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
