ALTER TABLE calendar_events ADD COLUMN activity_id INTEGER REFERENCES activities(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX ix_calendar_events_activity_id ON calendar_events(activity_id);
UPDATE calendar_events SET activity_id = (SELECT MIN(a.id) FROM activities a WHERE a.skill_id = calendar_events.skill_id AND a.date = calendar_events.date)
WHERE activity_id IS NULL AND deleted_at IS NULL AND id = (SELECT MIN(d.id) FROM calendar_events d WHERE d.skill_id = calendar_events.skill_id AND d.date = calendar_events.date AND d.deleted_at IS NULL);
UPDATE calendar_events SET completed = (SELECT completion = 100 FROM activities WHERE id = calendar_events.activity_id) WHERE activity_id IS NOT NULL;
INSERT INTO calendar_events (task_id,title,description,date,notes,priority,completed,created_at,skill_id,activity_id)
SELECT NULL,s.name,'',a.date,COALESCE(a.notes,''),'Medium',a.completion = 100,COALESCE(a.created_at,CURRENT_TIMESTAMP),a.skill_id,a.id FROM activities a JOIN skills s ON s.id=a.skill_id WHERE NOT EXISTS (SELECT 1 FROM calendar_events d WHERE d.activity_id=a.id);
INSERT OR IGNORE INTO daily_skill_seeds (skill_id,date) SELECT skill_id,date FROM activities;
