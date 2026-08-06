# DFAT — Digital Forensics Automation Tool

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pending-lightgrey)](#)
[![Mypy](https://img.shields.io/badge/mypy-strict-blue)](#)

DFAT (Digital Forensics Automation Tool with AI-Assisted Evidence Analysis) is an MSc Cybersecurity research project that implements a local-first forensic evidence processing pipeline spanning five stages: Acquisition, Artefact Parsing, AI Triage/NLP (local LLaMA-3), Dual-Output Reporting, and Benchmark Evaluation against DFRWS/CFReDS ground truth.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
# Optional forensic libraries:
pip install -e ".[forensic]"
```

Or use the helper script:

```bash
bash scripts/setup_dev.sh
```

## Quickstart

```bash
# Placeholder — pipeline CLI and API are implemented in later prompts.
python -m dfat
make run-api
```

## Project Structure

```
dfat/
├── src/dfat/           # Application packages (domain, engines, API, infrastructure)
├── tests/              # Unit, integration, and fixture data
├── config/             # Hierarchical YAML configuration
├── docs/               # Architecture, API, user, and development docs
├── scripts/            # Developer setup and utility scripts
└── data/               # Runtime evidence/outputs (gitignored)
```

## License

MIT License.

## Acknowledgments

Developed as postgraduate research at Canterbury Christ Church University (CCCU), with supervisory acknowledgment to Dr. Mandy Qi.
