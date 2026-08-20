# Contributing

Contributions can add a seed, improve a discovery query, or promote a
machine-discovered candidate.

Every approved catalog entry must include:

- a normalized target;
- at least one ecosystem category;
- a repository kind;
- at least one public evidence URL; and
- `status: "approved"`.

Run these checks before opening a pull request:

~~~console
python scripts/render.py
python scripts/validate.py
python -m unittest discover -s tests -v
~~~

Do not add `*.example.com` syntax. Use `.example.com` for a suffix match.
Avoid broad shared hosts such as `github.com`, `gitlab.com`,
`amazonaws.com`, and `storage.googleapis.com` unless a safe path-specific
policy is documented.
