"""One logged activity is edited through one daily task; no duplicate time records."""
from sqlalchemy.dialects.sqlite import insert
from models import db, Activity, DailyTask, DailySkillSeed, Skill


def visible_activity():
    return ~Activity.daily.has(DailyTask.deleted_at.is_not(None))


def activity_to_daily(activity):
    item = activity.daily
    if item is None:
        item = DailyTask.query.filter_by(skill_id=activity.skill_id, date=activity.date,
                                         activity_id=None, deleted_at=None, task_id=None).order_by(DailyTask.id).first()
        if item is None:
            item = DailyTask(title=db.session.get(Skill, activity.skill_id).name, date=activity.date)
            db.session.add(item)
        item.activity = activity
    item.skill_id, item.date = activity.skill_id, activity.date
    item.completed = activity.completion == 100
    item.notes = activity.notes
    db.session.execute(insert(DailySkillSeed).values(skill_id=activity.skill_id, date=activity.date).on_conflict_do_nothing())
    return item


def sync_daily_activity(item):
    if item.activity:
        item.activity.date = item.date
        item.activity.skill_id = item.skill_id
        item.activity.notes = item.notes
        db.session.execute(insert(DailySkillSeed).values(skill_id=item.skill_id, date=item.date).on_conflict_do_nothing())
