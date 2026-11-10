---
id: project:security
title: Reporting Technical Problems
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Reporting Technical Problems

## Orientation

Help preserve a dependable local research workflow.

## Text

### Report a reproducible issue

Provide the release version, command, minimal synthetic input, expected behavior and observed result. Remove credentials and personal data before sharing a report.

### Scope

The repository's tools inspect local files, assemble reference packets and export data. They are not a hosted inference service and do not require account credentials. Report path-boundary problems, unexpected writes, data leakage and validation errors through the facilities available on the hosting repository.

### Review external changes

Inspect a proposed code change before executing it. Continuous integration runs with read-only repository permissions and does not deploy or start model training. A passing check concerns its stated scope.

### Version a fix

Keep a minimal reproduction, repair the affected behavior and repeat the relevant checks. Preserve the original failure as evidence. Publish a clear affected-version statement when a technical issue warrants it.

## Connections

- [Contributor workflow](CONTRIBUTING.md)
- [Tool reference](docs/tools.md)

Silentium Regit Omnia.
