-- Run only after reviewing Tier A yield and a separate dry-run estimate.
-- Set maximum bytes billed before execution; LIMIT is not a scan-cost cap.
SELECT
  f.repo_name AS repo_name,
  f.path AS path,
  c.content AS content
FROM `bigquery-public-data.github_repos.files` AS f
JOIN `bigquery-public-data.github_repos.sample_contents` AS c
  ON f.id = c.id
WHERE REGEXP_CONTAINS(
  f.path,
  r'(?i)(^|/)(package\.json|pom\.xml|requirements[^/]*\.txt|pyproject\.toml|build\.gradle(?:\.kts)?|[^/]+\.csproj|Directory\.Packages\.props)$'
)
  AND c.binary IS NOT TRUE
