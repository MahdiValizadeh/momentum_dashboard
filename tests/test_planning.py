"""Integration tests use real SQLite files and Flask requests, never the user's data."""
import json
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
from models import db, Task, DailyTask, Subtask, Comment, ActivityLog, Skill, Activity
from migrate import upgrade


class PlanningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'test.db'
        self.config = {'TESTING': True, 'AUTO_DAILY_SKILLS': False, 'SECRET_KEY': 'test-only', 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(self.database)}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.csrf = session['_csrf']

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temp.cleanup()

    def post(self, path, data=None, follow=True):
        return self.client.post(path, data={**(data or {}), 'csrf_token': self.csrf}, follow_redirects=follow)

    def task(self, **fields):
        r = self.post('/tasks/new', {'title': 'Server monitoring', 'priority': 'High', 'status': 'To Do', 'manual_progress': 15, **fields}, follow=False)
        self.assertEqual(r.status_code, 302)
        return int(r.location.split('/')[-1])

    def daily(self, **fields):
        r = self.post('/daily-tasks/new', {'title': 'Configure metrics', 'date': date.today().isoformat(), 'priority': 'Medium', **fields}, follow=False)
        self.assertEqual(r.status_code, 302)
        return int(r.location.split('/')[-1])

    def test_pages_and_legacy_charts(self):
        for path in ('/', '/insights', '/activities', '/skills', '/tasks', '/tasks/new', '/daily-tasks/new', '/api/chart-data'):
            self.assertEqual(self.client.get(path, follow_redirects=True).status_code, 200, path)
        self.assertEqual(len(self.client.get('/api/chart-data').json['week_labels']), 7)

    def test_legacy_activity_crud_and_statistics(self):
        with self.app.app_context(): skill = Skill.query.first().id
        form = dict(skill_id=skill, date=date.today().isoformat(), minutes=45, quality=8, completion=75, notes='Original feature')
        self.assertEqual(self.post('/activities/add', form).status_code, 200)
        with self.app.app_context():
            activity = Activity.query.one()
            aid = activity.id
            self.assertEqual(activity.minutes, 45)
        self.assertEqual(self.client.get('/api/chart-data').json['week_minutes'][-1], 45)
        self.post(f'/activities/edit/{aid}', {**form, 'minutes': 60})
        self.assertEqual(self.client.get('/api/chart-data').json['week_minutes'][-1], 60)
        self.post(f'/activities/delete/{aid}')
        with self.app.app_context(): self.assertEqual(Activity.query.count(), 0)

    def test_create_daily_tasks_and_reload(self):
        first = self.daily()
        second = self.daily(title='Study CCNP', notes='Read chapter 1')
        with self.app.app_context():
            self.assertEqual(db.session.get(DailyTask, second).notes, 'Read chapter 1')
        page = self.client.get('/').data
        self.assertIn(b'Study CCNP', page)
        other = create_app(self.config)
        self.assertIn(b'Study CCNP', other.test_client().get('/').data)
        with other.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_daily_move_keeps_parent(self):
        task = self.task()
        item = self.daily(task_id=task)
        tomorrow = (date.today()+timedelta(days=1)).isoformat()
        response = self.client.post(f'/api/daily-tasks/{item}/move', json={'date':tomorrow}, headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            daily = db.session.get(DailyTask, item)
            self.assertEqual(str(daily.date), tomorrow)
            self.assertEqual(daily.task_id, task)
            self.assertTrue(any('moved' in entry.message for entry in daily.task.logs))

    def test_event_complete_and_reopen_does_not_complete_task(self):
        task = self.task(status='In Progress')
        event = self.daily(task_id=task)
        self.post(f'/daily-tasks/{event}/action',{'action':'toggle'})
        with self.app.app_context():
            self.assertTrue(db.session.get(DailyTask,event).completed)
            self.assertEqual(db.session.get(Task,task).status,'In Progress')
        self.post(f'/daily-tasks/{event}/action',{'action':'toggle'})
        with self.app.app_context(): self.assertFalse(db.session.get(DailyTask,event).completed)

    def test_completed_hidden_and_reopen_restores_previous_status(self):
        task = self.task(title='Unique parent title',status='On Hold')
        event = self.daily(title='Unique child title',task_id=task)
        self.post(f'/tasks/{task}/comments',{'body':'Persistent note'})
        self.post(f'/tasks/{task}/action',{'action':'status','status':'Completed'})
        page = self.client.get('/').data
        self.assertNotIn(b'Unique child title',page)
        self.assertNotIn(b'Unique parent title',page)
        self.assertNotIn(b'Unique parent title',self.client.get('/tasks').data)
        self.assertIn(b'Unique parent title',self.client.get('/tasks?status=Completed').data)
        self.assertIn(b'Persistent note',self.client.get(f'/tasks/{task}').data)
        self.post(f'/tasks/{task}/action',{'action':'reopen'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Task,task).status,'On Hold')
            self.assertEqual(Comment.query.count(),1)
        self.assertIn(b'Unique child title',self.client.get('/').data)

    def test_subtask_progress_and_history(self):
        task = self.task()
        self.post(f'/tasks/{task}/subtasks',{'title':'Install collector'})
        self.post(f'/tasks/{task}/subtasks',{'title':'Create dashboard'})
        with self.app.app_context(): ids = [s.id for s in Subtask.query.all()]
        self.post(f'/subtasks/{ids[0]}',{'action':'toggle'})
        with self.app.app_context(): self.assertEqual(db.session.get(Task,task).progress,50)
        self.post(f'/subtasks/{ids[1]}',{'action':'toggle'})
        with self.app.app_context():
            t = db.session.get(Task,task)
            self.assertEqual(t.progress,100)
            self.assertEqual(t.status,'To Do')
            self.assertEqual(sum('Subtask completed' in x.message for x in t.logs),2)
        self.post(f'/subtasks/{ids[1]}',{'action':'toggle'})
        self.post(f'/subtasks/{ids[0]}',{'action':'edit','title':'Changed step'})
        self.post(f'/subtasks/{ids[1]}',{'action':'delete'})
        with self.app.app_context():
            self.assertEqual(Subtask.query.count(),1)
            self.assertEqual(Subtask.query.one().title,'Changed step')

    def test_comments_edit_delete_order_and_escape(self):
        task = self.task()
        self.post(f'/tasks/{task}/comments',{'body':'First note'})
        self.post(f'/tasks/{task}/comments',{'body':'<script>alert(1)</script>'})
        page = self.client.get(f'/tasks/{task}').data
        self.assertIn(b'&lt;script&gt;',page)
        self.assertNotIn(b'<script>alert(1)</script>',page)
        self.assertLess(page.index(b'First note'),page.index(b'&lt;script&gt;'))
        with self.app.app_context(): comment = Comment.query.order_by(Comment.id).first().id
        self.post(f'/comments/{comment}',{'action':'edit','body':'Edited note'})
        with self.app.app_context(): self.assertIsNotNone(db.session.get(Comment,comment).updated_at)
        self.post(f'/comments/{comment}',{'action':'delete'})
        with self.app.app_context(): self.assertEqual(Comment.query.count(),1)

    def test_archive_task_retains_everything(self):
        task = self.task()
        event = self.daily(task_id=task)
        self.post(f'/tasks/{task}/comments',{'body':'Keep this'})
        self.post(f'/tasks/{task}/subtasks',{'title':'Keep step'})
        self.post(f'/tasks/{task}/action',{'action':'archive'})
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Task,task).deleted_at)
            for cls in (DailyTask,Comment,Subtask): self.assertEqual(cls.query.count(),1)
        self.assertIn(b'Server monitoring',self.client.get('/tasks?status=Archived').data)
        self.assertEqual(self.post(f'/tasks/{task}/comments',{'body':'No edit'}).status_code,400)
        self.post(f'/tasks/{task}/action',{'action':'restore'})
        with self.app.app_context(): self.assertIsNone(db.session.get(Task,task).deleted_at)

    def test_delete_event_preserves_parent_and_history(self):
        task = self.task()
        event = self.daily(task_id=task)
        self.post(f'/daily-tasks/{event}/action',{'action':'delete'})
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(DailyTask,event).deleted_at)
            self.assertEqual(Task.query.count(),1)
            self.assertTrue(any('delete' in x.message for x in db.session.get(Task,task).logs))
        self.post(f'/daily-tasks/{event}/action',{'action':'restore'})
        with self.app.app_context(): self.assertIsNone(db.session.get(DailyTask,event).deleted_at)

    def test_task_validation_does_not_write(self):
        for fields in [dict(title=''),dict(priority='Bad'),dict(status='Bad'),dict(manual_progress=101),dict(manual_progress='x'),dict(start_date='2026-12-02',due_date='2026-12-01'),dict(skill_id=999),dict(due_date='bad')]:
            data = dict(title='Invalid',priority='Medium',status='To Do',manual_progress=0)
            data.update(fields)
            self.assertEqual(self.post('/tasks/new',data).status_code,400,fields)
        with self.app.app_context(): self.assertEqual(Task.query.count(),0)

    def test_event_validation_does_not_write(self):
        for fields in [dict(title=''),dict(date='bad'),dict(task_id=999),dict(priority='Bad')]:
            data = dict(title='Invalid event',date=date.today().isoformat())
            data.update(fields)
            self.assertEqual(self.post('/daily-tasks/new',data).status_code,400,fields)
        with self.app.app_context(): self.assertEqual(DailyTask.query.count(),0)

    def test_task_edit_logs_deadline_priority_and_status(self):
        task = self.task()
        self.post(f'/tasks/{task}/edit',dict(title='Updated task',description='More detail',due_date='2027-01-01',priority='Urgent',status='In Progress',manual_progress=40))
        with self.app.app_context():
            t = db.session.get(Task,task)
            self.assertEqual(t.progress,40)
            messages=' '.join(x.message for x in t.logs)
            for field in ['Due Date','Priority','Status']: self.assertIn(field,messages)

    def test_event_edit_date_and_unlink(self):
        task = self.task()
        event = self.daily(task_id=task)
        r=self.post(f'/daily-tasks/{event}/edit',dict(title='Moved activity',description='More detail',date='2027-01-01',priority='Urgent',task_id=''))
        self.assertEqual(r.status_code,200)
        with self.app.app_context():
            e=db.session.get(DailyTask,event)
            self.assertIsNone(e.task_id)
            self.assertEqual(str(e.date),'2027-01-01')
            self.assertEqual(Task.query.count(),1)

    def test_overdue_and_due_soon(self):
        task=self.task(due_date=(date.today()-timedelta(days=1)).isoformat())
        other=self.task(title='Soon',due_date=(date.today()+timedelta(days=2)).isoformat())
        with self.app.app_context():
            self.assertTrue(db.session.get(Task,task).overdue)
            self.assertTrue(db.session.get(Task,other).due_soon)
        self.assertIn(b'Overdue',self.client.get('/tasks').data)

    def test_csrf_and_invalid_move(self):
        fresh = self.app.test_client()
        self.assertEqual(fresh.post('/tasks/new', data={'title':'No session','csrf_token':'!'}).status_code,400)
        self.assertEqual(self.client.post('/tasks/new',data={'title':'No token'}).status_code,400)
        event=self.daily()
        for payload in [[],{}, {'date':'invalid'}]:
            r=self.client.post(f'/api/daily-tasks/{event}/move',json=payload,headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(r.status_code,400)
        self.assertEqual(self.client.post(f'/api/daily-tasks/{event}/move',json={'date':'2027-01-01'}).status_code,400)

    def test_skills_remain_independent(self):
        self.post('/skills/add', {'name': 'Networks', 'color': '#6366f1'})
        with self.app.app_context():
            sid = Skill.query.filter_by(name='Networks').one().id
        task = self.task(skill_id=sid)
        self.post('/skills/delete/' + str(sid))
        with self.app.app_context():
            self.assertIsNone(db.session.get(Task, task).skill_id)
            self.assertEqual(Task.query.count(), 1)

    def test_calendar_weeks_and_filter_validation(self):
        self.assertEqual(self.client.get('/?week=2026-11-17').status_code,200)
        self.assertIn(b'2026-11-14',self.client.get('/?week=2026-11-17').data)
        for path in ['/?week=invalid','/?week=0001-01-01','/tasks?status=invalid']:
            self.assertEqual(self.client.get(path).status_code,400)

    def test_weekly_board_has_seven_lists_and_no_scheduling(self):
        page = self.client.get('/').data.decode()
        self.assertEqual(page.count('class="day-card '), 7)
        self.assertEqual(page.count('class="quick-add"'), 7)
        self.assertEqual(page.count('class="today-tag"'), 1)
        for obsolete in ('time-grid', 'hour-slot', 'start_time', 'end_time', 'Schedule', '/projects'):
            self.assertNotIn(obsolete, page)
        self.assertIn('Previous Week', page)
        self.assertIn('Next Week', page)

    def test_reopen_is_idempotent(self):
        task = self.task(status='In Progress')
        self.post(f'/tasks/{task}/action', {'action': 'reopen'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Task, task).status, 'In Progress')
        self.post(f'/tasks/{task}/action', {'action': 'status', 'status': 'Completed'})
        for _ in range(2):
            self.post(f'/tasks/{task}/action', {'action': 'reopen'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Task, task).status, 'In Progress')

    def test_edit_event_retains_completed_or_archived_parent(self):
        task = self.task()
        event = self.daily(task_id=task)
        for action in ({'action': 'status', 'status': 'Completed'}, {'action': 'archive'}):
            self.post(f'/tasks/{task}/action', action)
            page = self.client.get(f'/daily-tasks/{event}/edit').data.decode()
            self.assertIn(f'value="{task}" selected', page)
            response = self.post(f'/daily-tasks/{event}/edit', {
                'title': 'Corrected note', 'date': date.today().isoformat(), 'task_id': task})
            self.assertEqual(response.status_code, 200)
            with self.app.app_context():
                self.assertEqual(db.session.get(DailyTask, event).task_id, task)
            self.assertNotIn(b'Corrected note', self.client.get('/').data)
            self.assertEqual(self.post('/daily-tasks/new', {
                'title': 'Invalid link', 'date': date.today().isoformat(), 'task_id': task}).status_code, 400)

    def test_project_management_removed(self):
        self.assertEqual(self.client.get('/projects').status_code, 404)
        self.assertEqual(self.post('/projects', {'name': 'Removed'}).status_code, 404)
        for path in ('/', '/tasks', '/tasks/new'):
            page = self.client.get(path).data
            self.assertNotIn(b'project_id', page)
            self.assertNotIn(b'/projects', page)

    def test_quick_add_json_checkbox_and_daily_counts(self):
        response = self.client.post('/daily-tasks/quick-add', data={
            'title': 'Read 10 pages', 'date': str(date.today()), 'csrf_token': self.csrf},
            headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 201)
        item = response.json['id']
        self.assertIn('Read 10 pages', response.json['html'])
        for completed in ('1', '1', '0'):
            response = self.client.post(f'/daily-tasks/{item}/action', data={
                'action': 'toggle', 'completed': completed, 'csrf_token': self.csrf},
                headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['completed'], completed == '1')
            with self.app.app_context():
                self.assertEqual(db.session.get(DailyTask, item).completed, completed == '1')
        page = self.client.get('/').data
        self.assertIn(b'data-week-left>1</strong>', page)
        self.assertIn(b'data-week-done>0</strong>', page)
        self.assertIn(b'data-left>1</b>', page)

    def test_quick_add_validation_csrf_and_escaping(self):
        for fields in ({'title': '', 'date': str(date.today())},
                       {'title': 'Test', 'date': 'bad'},
                       {'title': 'x' * 201, 'date': str(date.today())}):
            response = self.client.post('/daily-tasks/quick-add', data={**fields, 'csrf_token': self.csrf}, headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.json)
        self.assertEqual(self.client.post('/daily-tasks/quick-add', data={'title':'No token'}).status_code, 400)
        self.post('/daily-tasks/quick-add', {'title': '<script>alert(1)</script>', 'date': str(date.today())})
        page = self.client.get('/').data
        self.assertIn(b'&lt;script&gt;', page)
        self.assertNotIn(b'<script>alert(1)</script>', page)
        with self.app.app_context(): self.assertEqual(DailyTask.query.count(), 1)

    def test_daily_details_edit_notes_and_creation_date(self):
        item = self.daily(title='Exercise')
        with self.app.app_context(): created = db.session.get(DailyTask, item).created_at
        response = self.post(f'/daily-tasks/{item}/edit', {
            'title': 'Exercise outdoors', 'date': '2026-12-12',
            'description': 'Walk for 30 minutes', 'notes': 'Bring water', 'priority': 'High'})
        self.assertEqual(response.status_code, 200)
        for value in (b'Exercise outdoors', b'Walk for 30 minutes', b'Bring water', b'Created'):
            self.assertIn(value, response.data)
        with self.app.app_context():
            daily = db.session.get(DailyTask, item)
            self.assertEqual(daily.created_at, created)
            self.assertEqual(daily.notes, 'Bring water')
            self.assertEqual(str(daily.date), '2026-12-12')
        self.assertNotIn(b'Exercise outdoors', self.client.get('/?week=2026-11-17').data)
        self.assertIn(b'Exercise outdoors', self.client.get('/?week=2026-12-12').data)

    def test_daily_notes_validation_and_deleted_detail(self):
        item = self.daily()
        response = self.post(f'/daily-tasks/{item}/edit', {'title':'Test','date':str(date.today()),'notes':'x'*20001})
        self.assertEqual(response.status_code, 400)
        self.post(f'/daily-tasks/{item}/action', {'action':'delete'})
        page = self.client.get(f'/daily-tasks/{item}').data
        self.assertIn(b'Restore task', page)
        self.assertNotIn(b'Configure metrics', self.client.get('/').data)
        self.post(f'/daily-tasks/{item}/action', {'action':'restore'})
        self.assertIn(b'Configure metrics', self.client.get('/').data)

    def test_old_event_urls_still_reach_daily_tasks(self):
        item = self.daily()
        self.assertEqual(self.client.get(f'/events/{item}').status_code, 200)
        self.assertEqual(self.client.get(f'/events/{item}/edit').status_code, 200)
        self.assertNotIn(b'start_time', self.client.get('/events/new').data)

    def test_permanent_task_delete_removes_all_dependents_only(self):
        target = self.task(title='Delete this')
        keep = self.task(title='Keep this')
        child = self.daily(task_id=target, notes='Child notes')
        deleted_child = self.daily(task_id=target)
        independent = self.daily(title='Independent')
        other_child = self.daily(task_id=keep)
        self.post(f'/tasks/{target}/comments', {'body': 'Remove comment'})
        self.post(f'/tasks/{target}/subtasks', {'title': 'Remove step'})
        self.post(f'/tasks/{keep}/comments', {'body': 'Keep comment'})
        self.post(f'/daily-tasks/{deleted_child}/action', {'action': 'delete'})
        self.post(f'/tasks/{target}/action', {'action': 'archive'})
        self.assertEqual(self.client.get(f'/tasks/{target}/delete').status_code, 200)
        self.assertEqual(self.post(f'/tasks/{target}/delete', {'confirm': 'delete'}).status_code, 200)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Task, target))
            self.assertIsNone(db.session.get(DailyTask, child))
            self.assertIsNone(db.session.get(DailyTask, deleted_child))
            for cls in (Comment, Subtask, ActivityLog):
                self.assertEqual(cls.query.filter_by(task_id=target).count(), 0)
            self.assertIsNotNone(db.session.get(Task, keep))
            self.assertIsNotNone(db.session.get(DailyTask, independent))
            self.assertIsNotNone(db.session.get(DailyTask, other_child))
            self.assertEqual(Comment.query.filter_by(task_id=keep).count(), 1)
            self.assertEqual(db.session.execute(db.text('PRAGMA foreign_key_check')).all(), [])
        self.assertEqual(self.client.get(f'/tasks/{target}').status_code, 404)

    def test_permanent_delete_requires_csrf_and_confirmation(self):
        task = self.task()
        self.assertEqual(self.client.post(f'/tasks/{task}/delete', data={'confirm':'delete'}).status_code, 400)
        self.assertEqual(self.post(f'/tasks/{task}/delete').status_code, 400)
        with self.app.app_context(): self.assertIsNotNone(db.session.get(Task, task))

    def test_skill_defaults_once_per_day_and_persistent_deletion(self):
        self.app.config['AUTO_DAILY_SKILLS'] = True
        self.client.get('/?week=2026-11-17')
        self.client.get('/?week=2026-11-17')
        with self.app.app_context():
            count = Skill.query.count() * 7
            self.assertEqual(DailyTask.query.count(), count)
            item = DailyTask.query.first()
            item_id = item.id
            self.assertEqual(item.title, item.skill.name)
        self.post(f'/daily-tasks/{item_id}/action', {'action': 'toggle', 'completed': '1'}, follow=False)
        self.client.get('/?week=2026-11-17')
        with self.app.app_context(): self.assertTrue(db.session.get(DailyTask, item_id).completed)
        self.post(f'/daily-tasks/{item_id}/action', {'action': 'delete'}, follow=False)
        self.client.get('/?week=2026-11-17')
        with self.app.app_context():
            self.assertEqual(DailyTask.query.count(), count)
            self.assertIsNotNone(db.session.get(DailyTask, item_id).deleted_at)
            self.assertEqual(Activity.query.count(), 0)
        self.post('/skills/add', {'name': 'CCNP', 'color': '#123456'}, follow=False)
        self.client.get('/?week=2026-11-17')
        with self.app.app_context(): self.assertEqual(DailyTask.query.count(), count + 7)

    def test_moved_or_parent_deleted_defaults_do_not_reappear(self):
        self.app.config['AUTO_DAILY_SKILLS'] = True
        self.client.get('/?week=2026-11-17')
        with self.app.app_context():
            item = DailyTask.query.first()
            item_id, skill_id, original_date = item.id, item.skill_id, item.date
            count = DailyTask.query.count()
        parent = self.task()
        self.post(f'/daily-tasks/{item_id}/edit', {'title':'My practice','date':'2026-12-01','task_id':parent})
        self.client.get('/?week=2026-11-17')
        with self.app.app_context():
            self.assertEqual(DailyTask.query.count(), count)
            self.assertEqual(DailyTask.query.filter_by(skill_id=skill_id,date=original_date).count(), 0)
        self.post(f'/tasks/{parent}/delete', {'confirm':'delete'}, follow=False)
        self.client.get('/?week=2026-11-17')
        with self.app.app_context(): self.assertEqual(DailyTask.query.count(), count-1)

    def test_stacked_skill_minutes_exact_totals_and_colors(self):
        with self.app.app_context():
            first, second = Skill.query.order_by(Skill.id).limit(2).all()
            for skill, minutes in [(first, 5), (first, 3), (second, 12)]:
                db.session.add(Activity(skill_id=skill.id,date=date.today(),minutes=minutes,quality=8,completion=100))
            db.session.add(Activity(skill_id=first.id,date=date.today()-timedelta(days=8),minutes=99,quality=7,completion=100))
            db.session.commit()
            ids, colors = (first.id,second.id), (first.color,second.color)
        data = self.client.get('/api/chart-data').json
        stacks = {row['skill_id']: row for row in data['week_skill_datasets']}
        self.assertEqual(stacks[ids[0]]['data'][-1], 8)
        self.assertEqual(stacks[ids[1]]['data'][-1], 12)
        self.assertEqual(stacks[ids[0]]['backgroundColor'], colors[0])
        self.assertEqual(stacks[ids[1]]['backgroundColor'], colors[1])
        for index, total in enumerate(data['week_minutes']):
            self.assertEqual(sum(row['data'][index] for row in stacks.values()), total)
        self.assertEqual(data['week_minutes'][-1], 20)
        self.assertEqual(sum(data['skill_minutes']), 119)

    def test_unified_dashboard_order_and_insights_redirect(self):
        response = self.client.get('/insights')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/')
        page = self.client.get('/').data.decode()
        for text in ['Current Streak', 'Minutes — Last 7 Days', 'Time Distribution by Skill', 'Quality &amp; Completion Trend']:
            self.assertIn(text, page)
        self.assertLess(page.index('Current Streak'), page.index('id="weekChart"'))
        self.assertLess(page.index('id="skillChart"'), page.index('class="weekly-board'))
        self.assertNotIn('href="/insights"', page)
        self.assertEqual(page.count('id="weekChart"'), 1)

    def test_migrations_idempotent_and_legacy_preservation(self):
        legacy=Path(self.temp.name)/'legacy.db'
        with sqlite3.connect(legacy) as c:
            c.executescript((Path(__file__).parents[1]/'migrations/001_legacy.sql').read_text())
            c.execute("INSERT INTO skills(id,name,color) VALUES (1,'Existing','#abcdef')")
            c.execute("INSERT INTO activities(id,skill_id,date,minutes,quality,completion,notes) VALUES (1,1,'2026-11-01',60,8,75,'Keep me')")
        app=create_app({**self.config,'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(legacy)})
        with app.app_context():
            upgrade()
            self.assertEqual(Activity.query.one().notes,'Keep me')
            self.assertEqual(Skill.query.count(),1)
            self.assertEqual(db.session.execute(db.text('select count(*) from schema_migrations')).scalar(),6)
            db.session.remove()
            db.engine.dispose()
        self.assertEqual(len(list(legacy.parent.glob('legacy.db.pre-planning-*.bak'))),1)

    def test_planner_upgrade_preserves_legacy_project_time_and_history(self):
        from hashlib import sha256
        legacy = Path(self.temp.name) / 'planner.db'
        directory = Path(__file__).parents[1] / 'migrations'
        with sqlite3.connect(legacy) as connection:
            connection.execute('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)')
            for name in ('001_legacy', '002_planning'):
                sql = (directory / (name + '.sql')).read_text()
                connection.executescript(sql)
                connection.execute('INSERT INTO schema_migrations VALUES (?, ?, ?)', (name, sha256(sql.encode()).hexdigest(), '2026-11-01'))
            connection.execute("INSERT INTO projects VALUES (1,'Keep old project','Preserved',0)")
            connection.execute("INSERT INTO tasks(id,title,description,created_at,priority,status,previous_status,manual_progress,project_id) VALUES (1,'Old task','Keep text','2026-11-01 09:00:00','High','In Progress','To Do',20,1)")
            connection.execute("INSERT INTO calendar_events(id,task_id,title,description,date,start_time,end_time,priority,completed,created_at) VALUES (1,1,'Old timed item','Original description','2026-11-17','09:00:00','10:00:00','Medium',0,'2026-11-01 09:00:00')")
            connection.execute("INSERT INTO comments VALUES (1,1,'Keep comment','2026-11-01 09:00:00',NULL)")
            connection.execute("INSERT INTO subtasks VALUES (1,1,'Keep step',1)")
            connection.execute("INSERT INTO activity_logs VALUES (1,1,'Keep history','2026-11-01 09:00:00')")
            before = {table: connection.execute('SELECT * FROM ' + table).fetchall() for table in ('projects','tasks','calendar_events','comments','subtasks','activity_logs')}
        app = create_app({**self.config, 'SQLALCHEMY_DATABASE_URI':'sqlite:///' + str(legacy)})
        client = app.test_client()
        page = client.get('/?week=2026-11-17').data
        self.assertIn(b'Old timed item', page)
        self.assertNotIn(b'09:00', page)
        with sqlite3.connect(legacy) as connection:
            for table, rows in before.items():
                actual = connection.execute('SELECT * FROM ' + table).fetchall()
                if table == 'calendar_events': actual = [row[:len(rows[0])] for row in actual]
                self.assertEqual(rows, actual, table)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        with client.session_transaction() as session: token = session['_csrf']
        response = client.post('/daily-tasks/1/edit', data={'csrf_token': token, 'title':'Old timed item', 'date':'2026-11-18', 'task_id':'1', 'notes':'New note'})
        self.assertEqual(response.status_code, 302)
        with sqlite3.connect(legacy) as connection:
            self.assertEqual(connection.execute('SELECT start_time,end_time,notes FROM calendar_events').fetchone(), ('09:00:00','10:00:00','New note'))
            self.assertEqual(connection.execute('SELECT project_id FROM tasks').fetchone()[0], 1)
        with app.app_context():
            upgrade()
            db.session.remove()
            db.engine.dispose()
        self.assertEqual(len(list(legacy.parent.glob('planner.db.pre-planning-*.bak'))), 1)


if __name__ == '__main__':
    unittest.main()
