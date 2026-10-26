CREATE SCHEMA IF NOT EXISTS ${catalog}.ops;

CREATE TABLE IF NOT EXISTS ${catalog}.ops.milestones (
  team STRING,
  round INT,
  status STRING,
  metric_name STRING,
  metric_value DOUBLE,
  ts TIMESTAMP
);

CREATE SCHEMA IF NOT EXISTS ${catalog}.facilitator;

CREATE TABLE IF NOT EXISTS ${catalog}.facilitator.answer_key (
  team STRING,
  question_id STRING,
  expected_answer_json STRING,
  computed_at TIMESTAMP
);
