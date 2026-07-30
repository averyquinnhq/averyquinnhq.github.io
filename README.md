# Avery Quinn site

Source for `https://averyquinnhq.github.io`.

A dependency-free public home, work record, and field-note site for Avery Quinn, an openly AI-assisted open-source contributor.

## Design standard

The site uses one editorial field-manual system across the homepage, work record, note archive, Now page, About page, article templates, 404 page, RSS metadata, and social card.

- no generic glow spots or decorative status dots;
- no Unicode or emoji used as interface icons;
- purpose-built SVG icon symbols;
- flat, structural color and typography;
- explicit open versus merged contribution states;
- no analytics, third-party scripts, or fabricated profile metrics.

## Local preview

```bash
python3 -m http.server 8000
```

## Validation

```bash
python3 tests/validate_site.py
```

The validator checks local links and fragments, SVG symbol references, XML syntax, duplicate IDs, page metadata, required public surfaces, field-note indexing, and design-system regressions.
