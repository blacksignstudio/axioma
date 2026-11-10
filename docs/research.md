---
id: guide:research
title: Research Use and Experimental Design
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Research Use and Experimental Design

## Orientation

A testable research direction, with no claim that the proposed method has already improved a model.

## Text

### Three different uses

**Reading and context conditioning:** a model receives selected texts at inference time. **Dataset preparation:** synthetic demonstrations are formatted for a chosen training pipeline. **Parameter fine-tuning:** a separately authorized training run updates weights. Only the first two kinds of tools are implemented here.

### A fair comparison

Keep the model, task facts, generation settings and evaluation situations fixed. Compare a plain task prompt, a compact ordinary project brief, and an AXIOMA context packet. Match context budgets or report their difference. Randomize presentation order for human review where feasible.

Before collecting outputs, define the rubric: evidence fidelity, scope fidelity, useful completion, willingness to correct and preservation of an explicitly requested voice. Include countercases where a shorter answer is better. Retain failures and missing outputs in the denominator.

### Use the seed data carefully

The included train and evaluation examples are synthetic. Their IDs, prompts and scenario facts are separated within this repository. This does not establish absence from a model's wider pretraining history, and the set is too small to support broad claims about general capability.

```text
python -m axioma_context export --format messages --out build/train-messages.jsonl
python -m axioma_context export --format trl --out build/train-trl.jsonl
```

The second export has conversational prompt/completion columns described by [Hugging Face TRL](https://huggingface.co/docs/trl/main/en/dataset_formats). Export success establishes data shape, not compatibility with every trainer version, license of a chosen base model or completion of training.

### Evaluate actual responses

Store each actual response as one JSON object with `id` and `text` in a JSONL file under build/. Then run:

```text
python -m axioma_context evaluate --predictions build/predictions.jsonl
```

The local evaluator reports coverage and lexical probes. A phrase can occur in a wrong answer; a correct paraphrase can omit the selected phrase. Human semantic review is therefore required. The supplied reference predictions are a software fixture, not model outputs or a reported model score.

### Report a real experiment

Record model identity, version, settings, full prompts, corpus version, split, actual outputs, cost if any, judgment method and limitations. Claim an effect only after the relevant comparison. No API key, network inference, training job or paid infrastructure is required for the repository's local examples.

## Connections

- [Dataset card](../data/README.md)
- [Evaluation protocol](evaluation.md)
- [Context guide](context.md)
- [Brown et al., 2020](https://arxiv.org/abs/2005.14165)

Silentium Regit Omnia.
