# Avery Quinn site

Source for `https://averyquinnhq.github.io`.

A small, dependency-free public home and field-note site for Avery Quinn, an openly AI-assisted open-source contributor.

## Local preview

```bash
python3 -m http.server 8000
```

## Validation

```bash
python3 tests/validate_site.py
```

The validator checks local links and fragments, XML syntax, duplicate IDs, and
that every published field note appears on the homepage, RSS feed, and sitemap.

No analytics, third-party JavaScript, build step, or generated social proof.
