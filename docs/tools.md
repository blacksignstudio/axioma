---
id: guide:tools
title: Local Tool Reference
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Local Tool Reference

## Orientation

Commands operate on the checked-out repository and do not initiate model inference or publication.

## Text

### Inspect

`python -m axioma_context validate` checks the current release manifest and all Markdown routes. Errors return a nonzero exit status; the command does not repair files.

### Assemble context

`python -m axioma_context pack --ids guide:principles guide:context` emits complete reference texts. `--max-bytes` sets a UTF-8 byte budget. `--out build/context.txt` writes a new generated file. Existing outputs are not overwritten.

### Export demonstrations

`python -m axioma_context export --format messages` emits conversational training rows. `--format trl` emits prompt/completion rows. Evaluation rows are not included in training exports.

### Inspect response coverage

`python -m axioma_context evaluate --predictions build/predictions.jsonl` reads actual responses supplied by the researcher and reports missing cases and lexical probes. It never calls a model or treats the bundled reference fixture as observed model behavior.

### Maintain a changed edition

After a deliberate edit, inspect its diff and run `python tools/refresh_manifest.py`. This updates derived catalog and manifest digests. It does not authorize the edit, publish it or decide its literary merit. Then run the validator and tests again.

## Connections

- [Context setup](context.md)
- [Contribution guide](../CONTRIBUTING.md)
- [Research design](research.md)

Silentium Regit Omnia.
