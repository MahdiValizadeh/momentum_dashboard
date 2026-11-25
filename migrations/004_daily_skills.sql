ALTER TABLE calendar_events ADD COLUMN skill_id INTEGER REFERENCES skills(id) ON DELETE SET NULL;
CREATE INDEX ix_calendar_events_skill_id ON calendar_events(skill_id);
CREATE TABLE daily_skill_seeds (
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    PRIMARY KEY (skill_id, date)
);
