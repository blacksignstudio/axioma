---
id: guide:context
title: Using AXIOMA as Context
kind: guide
version: 2.0.0
language: en
license: CC-BY-4.0
---

# Using AXIOMA as Context

## Orientation

A practical entry that leaves the choice of task and environment with the reader.

## Text

### Read before assembling

Start with the project introduction and a complete text relevant to the task. Use the module guide to identify neighboring functions. The full corpus is a resource, not a compulsory context load.

### Install in an isolated environment

On Windows, direct executable paths avoid changing shell execution policy:

```text
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m axioma_context validate
```

On a Unix-like system:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m axioma_context validate
```

Python 3.10 or newer is the intended interface. The release's [verification record](../verification.json) distinguishes the environment actually exercised from planned CI coverage. It does not infer compatibility from a version number alone.

### Build a complete packet

Use the same environment interpreter as in the installation step. On Windows:

```text
.venv/Scripts/python.exe -m axioma_context pack --ids guide:principles guide:context --max-bytes 32768 --out build/context.txt
```

On a Unix-like system, use `.venv/bin/python` in place of `.venv/Scripts/python.exe`. Other guides shorten this executable path to `python`; use that shorthand only after activating the environment or selecting its interpreter explicitly.

The catalog gives each source an ID, path and digest. The packer checks the selected source bytes and refuses a packet larger than the requested budget. The budget is measured in UTF-8 bytes, not model tokens. A tokenizer and the actual model context window remain separate concerns.

### Apply and check

Give the reader the current task, relevant available facts and the packet as reference material. Ask for a useful result and its source basis. Document the model, prompt, settings, output and review method if you want a reproducible comparison.

Example: a missing appendix prevents a complete summary. A grounded response identifies the missing appendix, summarizes the accessible sections and labels the result partial. It neither invents the appendix nor abandons the verified material.

## Connections

- [Working principles](principles.md)
- [Research design](research.md)
- [Command reference](tools.md)

Silentium Regit Omnia.
