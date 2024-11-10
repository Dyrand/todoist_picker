DROP TABLE IF EXISTS choices;

CREATE TABLE choices (
  id TEXT PRIMARY KEY,
  type_of TEXT,
  parent_id TEXT,
  choice_name TEXT NOT NULL,
  choice_weight INTEGER NOT NULL
);