"""Tests for the 2026-11 improvements: skill archive/delete guard, weekly goals, export, pagination."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(__file__), "unused.db"))
from pathlib import Path
import tempfile
import unittest
from datetime import date

from app import create_app
from models import db, Skill, Activity


class ImprovementsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'test.db'
        self.config = {'TESTING': True, 'AUTO_DAILY_SKILLS': False, 'SECRET_KEY': 'test-only',
                       'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(self.database)}
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

    def add_skill_with_activity(self, name='Networks'):
        self.post('/skills/add', {'name': name, 'color': '#6366f1'})
        with self.app.app_context():
            sid = Skill.query.filter_by(name=name).one().id
        self.post('/activities/add', dict(skill_id=sid, date=date.today().isoformat(),
                                          minutes=30, quality=8, completion=100, notes=''))
        return sid

    def test_skill_with_activities_cannot_be_deleted(self):
        sid = self.add_skill_with_activity()
        self.post(f'/skills/delete/{sid}')
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Skill, sid))
            self.assertEqual(Activity.query.count(), 1)

    def test_skill_without_activities_can_be_deleted(self):
        self.post('/skills/add', {'name': 'Empty', 'color': '#000000'})
        with self.app.app_context():
            sid = Skill.query.filter_by(name='Empty').one().id
        self.post(f'/skills/delete/{sid}')
        with self.app.app_context():
            self.assertIsNone(db.session.get(Skill, sid))

    def test_archive_hides_skill_and_unarchive_restores(self):
        sid = self.add_skill_with_activity()
        self.post(f'/skills/archive/{sid}')
        page = self.client.get('/skills').data.decode()
        self.assertIn('Archived Skills', page)
        with self.app.app_context():
            self.assertTrue(db.session.get(Skill, sid).archived)
            self.assertEqual(Activity.query.count(), 1)  # history preserved
        self.post(f'/skills/unarchive/{sid}')
        with self.app.app_context():
            self.assertFalse(db.session.get(Skill, sid).archived)

    def test_weekly_target_and_dashboard_goals(self):
        sid = self.add_skill_with_activity()
        self.post(f'/skills/edit/{sid}', {'name': 'Networks', 'color': '#6366f1',
                                          'weekly_target_minutes': '120'})
        with self.app.app_context():
            self.assertEqual(db.session.get(Skill, sid).weekly_target_minutes, 120)
        page = self.client.get('/').data.decode()
        self.assertIn('Weekly Goals', page)
        self.assertIn('30 / 120 min', page)

    def test_csv_export(self):
        self.add_skill_with_activity()
        response = self.client.get('/export/activities.csv')
        self.assertEqual(response.status_code, 200)
        text = response.data.decode()
        self.assertIn('date,skill,minutes,quality,completion,notes', text)
        self.assertIn('Networks', text)

    def test_activities_pagination(self):
        sid = self.add_skill_with_activity()
        with self.app.app_context():
            for _ in range(30):
                db.session.add(Activity(skill_id=sid, date=date.today(), minutes=10, quality=5, completion=50, notes=''))
            db.session.commit()
        page1 = self.client.get('/activities').data.decode()
        self.assertIn('page 1 of 2', page1)
        page2 = self.client.get('/activities?page=2').data.decode()
        self.assertIn('page 2 of 2', page2)


if __name__ == '__main__':
    unittest.main()
