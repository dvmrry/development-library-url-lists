-- Inspect snapshot age and size before scanning content.
-- Table modification time is metadata, not proof that every file is current.
SELECT
  table_id,
  TIMESTAMP_MILLIS(last_modified_time) AS last_modified,
  size_bytes,
  row_count
FROM `bigquery-public-data.github_repos.__TABLES__`
WHERE table_id IN ('files', 'sample_contents', 'contents')
ORDER BY table_id
