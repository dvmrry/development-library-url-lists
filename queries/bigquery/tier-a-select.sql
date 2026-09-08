-- Dry-run this exact SELECT first. Set maximum bytes billed before execution.
-- Path filters reduce output, but do not guarantee a smaller content scan.
SELECT
  f.repo_name AS repo_name,
  f.path AS path,
  c.content AS content
FROM `bigquery-public-data.github_repos.files` AS f
JOIN `bigquery-public-data.github_repos.sample_contents` AS c
  ON f.id = c.id
WHERE REGEXP_CONTAINS(
  f.path,
  r'(?i)(^|/)(\.npmrc|\.yarnrc|\.yarnrc\.yml|pip\.conf|pip\.ini|\.condarc|environment\.yml|environment\.yaml|settings\.xml|NuGet\.Config|paket\.dependencies|Pipfile|bunfig\.toml)$'
)
  AND c.binary IS NOT TRUE
