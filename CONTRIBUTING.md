---
id: project:contributing
title: Contributing to AXIOMA
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Contributing to AXIOMA

## Orientation

Changes are welcome when they make the work clearer, more useful or more accountable to its sources.

## Text

### Choose the smallest sufficient change

Distinguish a typo, a translation correction, a technical repair, a new interpretation and a new function. Preserve the surrounding composition. Explain a change in meaning rather than hiding it inside formatting.

### Keep the document profile

Every Markdown document has one metadata block, one top-level title, the same three second-level sections and the required closing line. Deeper headings belong inside Text. Use English for public prose and ASCII paths. Keep links local where possible.

### Provide a concrete review

Give the source passage, proposed wording, purpose and an example or counterexample when relevant. Avoid claims of model performance without actual outputs and a comparison. Synthetic data should remain explicitly synthetic.

### Check the changed edition

```text
python tools/refresh_manifest.py
python -m axioma_context validate
python -m unittest discover -s tests -v
```

Read the diff after generated digests change. A successful structural check does not decide the literary argument.

### Preserve license scope

Only contribute material you can license under the applicable project terms. Text and data use CC BY 4.0; code uses MIT. Retain attribution and identify adaptations. Do not contribute private conversation, personal data or material from another project without appropriate permission.

## Connections

- [Editorial policy](docs/editorial-policy.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Tool reference](docs/tools.md)

Silentium Regit Omnia.
