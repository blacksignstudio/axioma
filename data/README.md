---
id: data:card
title: Synthetic Dataset Card
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Synthetic Dataset Card

## Orientation

A small seed collection for testing a research pipeline and designing later experiments.

## Text

### Contents and purpose

The training split contains thirty-two synthetic demonstrations across eight practical families: evidence, scoped action, correction, continuity, proportionate editing, interpretive plurality, closure and authorial voice. The evaluation split contains sixteen different synthetic situations across the same families.

### Origin and privacy

The examples were composed for this public edition. They are not client records, personal correspondence or measurements of a trained model. Source references point to public project guides. Text and data use CC BY 4.0.

### Intended use

Study the examples as demonstrations, export the training split as conversational messages or TRL prompt/completion rows, and collect actual responses on the evaluation split. Select any training model, tokenizer, hardware and training configuration separately.

### Split limits

The included train and evaluation prompts and scenario IDs are distinct. The eight skill families are intentionally shared between splits; this is not a family-held-out benchmark. A small synthetic set cannot establish broad generalization, natural-data representativeness or freedom from wider model contamination.

### Evaluation and fixtures

Each evaluation case includes a reference answer, limited lexical probes and a human review rubric. examples/reference_predictions.jsonl reproduces the reference answers as a software fixture. It is not a model's output and must not be reported as one.

### Check before reuse

Inspect every example for your domain, base-model license and evaluation purpose. A training export is a data artifact, not evidence that parameter fine-tuning occurred.

## Connections

- [Training data](train.jsonl)
- [Evaluation data](eval.jsonl)
- [Research protocol](../docs/research.md)
- [Evaluation protocol](../docs/evaluation.md)

Silentium Regit Omnia.
