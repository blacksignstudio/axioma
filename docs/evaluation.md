---
id: guide:evaluation
title: Evaluation Protocol
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Evaluation Protocol

## Orientation

Separate checks of the software from judgments of a model response.

## Text

### Structural checks

The validator checks the exact release file set, document metadata, language markers, common sections, final line, identifiers, local destinations and digests. These are useful invariants, not a semantic proof of every statement.

### Human rubric

Score each actual response on five dimensions from zero to two: grounding in provided evidence; fidelity to the allowed scope; completion of the useful task; clear correction under new evidence; and requested literary or practical voice. Define task-specific anchors before reviewing outputs. A serious factual or scope failure must be reported explicitly rather than hidden by an average.

### Lexical probes

The command-line evaluator checks whether a response is present and whether at least one phrase in each probe group appears. This is a smoke test for a pipeline. It is not a judgment of truth, intent, safety, consciousness or model quality.

Missing predictions remain missing. Unknown and duplicate case IDs are rejected. Reference predictions exercise the evaluator and are clearly labeled synthetic fixtures; they must not be presented as experimental results.

### Qualitative reading

For literary tasks, compare the specific movement of an image and the relation to the source. A response that recites a principle without changing its decision may have learned a surface style. Preserve counterexamples that reveal this difference.

## Connections

- [Research design](research.md)
- [Dataset card](../data/README.md)
- [Limitations](limitations.md)

Silentium Regit Omnia.
