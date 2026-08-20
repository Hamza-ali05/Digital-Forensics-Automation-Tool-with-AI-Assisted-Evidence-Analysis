# Ethical Compliance

This document summarises the ethical-compliance position of the DFAT dissertation artefact and its evaluation design.

## 1. CCCU FREC Approval Context

The project is framed as an MSc Cybersecurity research artefact under Canterbury Christ Church University. The intended ethical position is that usability evaluation and associated participant-facing materials are aligned with CCCU Faculty Research Ethics Committee expectations.

This repository records the technical controls that support that ethical position. It does not replace the institution's formal approval paperwork.

## 2. Participant Information and Consent

The usability-evaluation design assumes:
- participants receive an information sheet before participation
- the voluntary nature of participation is made explicit
- participants understand that the exercise evaluates the tool, not their competence
- participants are informed about storage, anonymisation, and destruction arrangements

Within the implementation, the questionnaire flow is kept separate from authenticated casework to reduce unnecessary identity linkage.

## 3. Informed Consent Process

The ethical intention is:
1. provide participant information in advance
2. obtain explicit consent before questionnaire participation
3. collect only the minimum data required for the research objective
4. allow data destruction in line with ethics commitments

The repository supports this by keeping the questionnaire response model minimal and anonymised.

## 4. Data Anonymisation

Anonymisation is implemented directly in code:
- `QuestionnaireInstrument.generate_participant_id()` generates UUID participant identifiers
- `ResponseCollector.collect_response()` stores only anonymised IDs
- export logic redacts obvious identifying text patterns from free-text responses

Relevant files:
- `src/dfat/evaluation/usability/questionnaire.py`
- `src/dfat/evaluation/usability/response_collector.py`

This means the dissertation evaluation can discuss usability outcomes without storing direct personal identifiers in the application layer.

## 5. Data Storage Expectations

The intended ethical storage model is:
- university-approved encrypted storage for research data
- restricted access to authorised researchers only
- separation of code repository content from live participant response data

Repository-level support:
- questionnaire response data directories are ignored from version control
- production configuration and secret-handling workflows discourage accidental leakage

Institutional specifics such as exact CCCU storage locations should be recorded in the dissertation's ethics appendix and participant documentation.

## 6. Data Destruction

Ethical data-destruction support is implemented through:
- `ResponseCollector.delete_all_responses()`

This exists specifically to support destruction requirements after the retention period or on approved ethics closure. Verification for this capability is recorded in:
- `reports/research_objectives_verification.json`
- `reports/feature_verification.json`

## 7. Use of Public Datasets Only

The benchmark-evaluation methodology is based on public datasets:
- DFRWS
- CFReDS

This avoids:
- live evidential sensitivity
- privacy exposure from operational cases
- consent complications associated with real-user devices

As a result, the dissertation can evaluate technical capability without handling real victim or suspect data.

## 8. Questionnaire Exposure and Risk Boundary

The questionnaire is intentionally accessible without login through the evaluation API and public frontend path. This supports participant convenience and reduces identity linkage.

The route-level ethical boundary is still protected by:
- minimal-data collection
- anonymised UUID participant IDs
- explicit response-destruction support

Administrative access remains required for results review and export.

## 9. AI Tool Usage and Academic Integrity

This project openly acknowledges AI use in the artefact:
- local LLaMA-3 integration
- documented AI limitations
- JSON primary record over narrative output
- explicit disclaimer handling in reports

For dissertation framing, the project should be presented as AI-assisted tooling rather than autonomous forensic decision-making. The human investigator remains responsible for interpretation.

Where the programme or university refers to AI usage levels, this implementation is consistent with a constrained, disclosed, assistive usage posture rather than hidden or unsupervised delegation.

## 10. Dual-Use Risk Acknowledgment

Digital-forensics tooling can create dual-use risk. Capabilities that support legitimate investigation could be misapplied if deployed irresponsibly.

Mitigations implemented in DFAT include:
- local-only LLM endpoint restriction
- audit logging
- role-based access control
- evidence integrity emphasis
- explicit documentation of limitations
- non-claim of autonomous evidential authority

The dissertation should acknowledge that the tool is intended for lawful, supervised, research-oriented forensic workflows only.

## 11. Summary of Ethical Controls in Code

The strongest ethics-relevant technical controls are:
- anonymised participant IDs via UUIDs
- redaction support for free-text questionnaire export
- deletion support through `ResponseCollector.delete_all_responses()`
- public benchmark datasets instead of real evidence
- AI disclaimer and limitation documentation
- auditability and RBAC in the wider application

## 12. Dissertation Usage Note

For dissertation submission, this document should be read together with:
- `docs/dissertation/LIMITATIONS.md`
- `docs/dissertation/EVALUATION_METHODOLOGY.md`
- `docs/user-guide/USER_MANUAL.md`
- `docs/operations/OPERATIONS_GUIDE.md`

These documents together provide the implementation-side evidence for the ethics narrative in the written dissertation.
