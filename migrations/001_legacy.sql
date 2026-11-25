CREATE TABLE IF NOT EXISTS skills (
	id INTEGER NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	color VARCHAR(20), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS activities (
	id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	date DATE NOT NULL, 
	minutes INTEGER NOT NULL, 
	quality INTEGER NOT NULL, 
	completion INTEGER NOT NULL, 
	notes TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(skill_id) REFERENCES skills (id)
);

CREATE INDEX IF NOT EXISTS ix_activities_date ON activities (date);
