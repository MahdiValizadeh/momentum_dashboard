CREATE TABLE IF NOT EXISTS projects (
	id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT NOT NULL, 
	archived BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS tasks (
	id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	start_date DATE, 
	due_date DATE, 
	priority VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	previous_status VARCHAR(20) NOT NULL, 
	manual_progress INTEGER NOT NULL, 
	deleted_at DATETIME, 
	project_id INTEGER, 
	skill_id INTEGER, 
	PRIMARY KEY (id), 
	CHECK (status IN ('To Do','In Progress','On Hold','Completed')), 
	CHECK (priority IN ('Low','Medium','High','Urgent')), 
	CHECK (manual_progress >= 0 AND manual_progress <= 100), 
	CHECK (due_date IS NULL OR start_date IS NULL OR due_date >= start_date), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_tasks_due_date ON tasks (due_date);

CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks (status);

CREATE TABLE IF NOT EXISTS activity_logs (
	id INTEGER NOT NULL, 
	task_id INTEGER NOT NULL, 
	message TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX IF NOT EXISTS ix_activity_logs_task_id ON activity_logs (task_id);

CREATE TABLE IF NOT EXISTS calendar_events (
	id INTEGER NOT NULL, 
	task_id INTEGER, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	date DATE NOT NULL, 
	start_time TIME, 
	end_time TIME, 
	priority VARCHAR(10) NOT NULL, 
	completed BOOLEAN NOT NULL, 
	deleted_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (priority IN ('Low','Medium','High','Urgent')), 
	CHECK ((start_time IS NULL AND end_time IS NULL) OR (start_time IS NOT NULL AND (end_time IS NULL OR end_time > start_time))), 
	FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX IF NOT EXISTS ix_calendar_events_date ON calendar_events (date);

CREATE INDEX IF NOT EXISTS ix_calendar_events_task_id ON calendar_events (task_id);

CREATE TABLE IF NOT EXISTS comments (
	id INTEGER NOT NULL, 
	task_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX IF NOT EXISTS ix_comments_task_id ON comments (task_id);

CREATE TABLE IF NOT EXISTS subtasks (
	id INTEGER NOT NULL, 
	task_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	completed BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX IF NOT EXISTS ix_subtasks_task_id ON subtasks (task_id);
