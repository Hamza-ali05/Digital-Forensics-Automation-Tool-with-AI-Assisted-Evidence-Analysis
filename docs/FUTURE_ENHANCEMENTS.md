# Future Enhancements

This roadmap documents future DFAT enhancements grounded in the literature review, the dissertation gap analysis, and the implementation boundaries acknowledged in `docs/dissertation/LIMITATIONS.md`.

Priority is assigned using three criteria:
- alignment with identified research gaps
- leverage of existing extension points in the current architecture
- likely value for the next dissertation or post-dissertation iteration

## Priority 1 — Immediate (Next Iteration)

### 1. ForensicLLM Fine-Tuning

**Rationale**

The current implementation uses a base local LLaMA-3 model. This directly reflects the limitation acknowledged from Sharma et al. (2025): a general-purpose model is less reliable than a forensic-domain fine-tuned model for classification, explanation, and investigative summarization.

**Implementation Approach**

- extend `LLMConfig` in `src/dfat/ai_engine/llm/config.py` with fields such as:
  - `fine_tuned_model_path`
  - `fine_tuned_model_name`
  - `model_family`
- derive supervised training examples from:
  - benchmark-comparison outputs in `src/dfat/evaluation/benchmark/`
  - false-positive / false-negative analysis from `BenchmarkComparator`
  - curated artefact-to-classification pairs
- add a model-selection path in:
  - `src/dfat/container.py`
  - `src/dfat/ai_engine/llm/client.py`
- preserve current fallback behavior through `RuleBasedAnalyzer`

**Estimated Effort**

High

**Dependencies on Current Architecture**

- `LLMConfig`
- prompt versioning via `PROMPT_VERSION`
- `HallucinationGuard`
- `RuleBasedAnalyzer`
- benchmark outputs for training-data generation

### 2. Network Packet Analysis

**Rationale**

The current scope includes network-connection artefacts from memory, but not full packet-level forensic analysis. This is a clear extension of the proposal's current scope limitation and would improve completeness for incident-response cases involving exfiltration, C2, and lateral movement.

**Implementation Approach**

- add `NETWORK_PACKET` to `ArtefactCategory` in `src/dfat/core/enums.py`
- create `NetworkPacketParser` implementing `IArtefactParser`
- place the parser under `src/dfat/forensic_engine/parsers/`
- integrate `pyshark` or Tshark/Wireshark-backed parsing
- add parser registration through the existing DI container and parser registry
- extend:
  - artefact explorer filters
  - IOC detection
  - timeline generation
  - benchmark mapping if packet-level datasets are added later

**Estimated Effort**

Medium to High

**Dependencies on Current Architecture**

- `IArtefactParser` in `src/dfat/core/interfaces/parser.py`
- `ParserRegistry`
- `ForensicOrchestrator`
- `ArtefactNormalizer`
- existing artefact explorer and IOC dashboard pages

### 3. Real-Time Dashboard Updates

**Rationale**

The current system uses polling for pipeline progress. Replacing this with WebSocket-based real-time updates would improve investigator experience and reduce unnecessary API traffic.

**Implementation Approach**

- add a FastAPI WebSocket endpoint for pipeline progress streaming
- emit progress updates from the pipeline job manager / progress tracker
- add a React `useWebSocket` hook and route-level subscription logic
- preserve polling as a fallback for constrained deployments

**Estimated Effort**

Medium

**Dependencies on Current Architecture**

- `ProgressTracker`
- `JobManager`
- `PipelineDetail` and related frontend pages
- monitoring and request-ID context for correlation

## Priority 2 — Medium Term

### 4. Cloud Evidence Support

**Rationale**

Many modern investigations involve evidence derived from cloud storage and SaaS platforms rather than only disk images and memory dumps. Extending evidence support would align DFAT more closely with current forensic practice.

**Implementation Approach**

- extend `EvidenceType` with cloud-focused evidence sources
- introduce `CloudEvidenceHandler`
- create cloud-specific parsers for exported metadata, activity logs, and object manifests
- preserve the same normalized artefact output format so downstream triage and reporting remain unchanged

**Estimated Effort**

High

**Dependencies on Current Architecture**

- `EvidenceType`
- acquisition handlers pattern in `src/dfat/forensic_engine/acquisition/`
- `IArtefactParser`
- `ArtefactNormalizer`
- evidence-management and case-linking workflows

### 5. Advanced Anomaly Detection

**Rationale**

Current prioritization is dominated by rule-based triage and LLM-assisted interpretation. A classical ML anomaly-detection layer could complement both by identifying unusual artefact distributions or outliers not explicitly encoded in rules.

**Implementation Approach**

- add an anomaly-scoring service using `scikit-learn`
- derive numerical features from normalized artefacts
- integrate anomaly scores into:
  - triage scoring
  - IOC dashboard ranking
  - investigator review workflows
- keep the model explainable and versioned

**Estimated Effort**

Medium to High

**Dependencies on Current Architecture**

- `ArtefactNormalizer`
- `ScoringEngine`
- `TriageAggregator`
- report metadata and benchmark evaluation for measuring benefit

### 6. Multi-Language Report Generation

**Rationale**

Current narrative output is English-centric. Multi-language reporting would increase accessibility for broader deployment and cross-jurisdiction presentation.

**Implementation Approach**

- extend report-generation settings with target locale support
- localize narrative templates
- add prompt-localization options for LLM-generated sections
- preserve the structured JSON report as language-neutral primary evidence

**Estimated Effort**

Medium

**Dependencies on Current Architecture**

- `NarrativeAssembler`
- template directories in the reporting layer
- `StructuredJSONExporter` as the stable non-localized evidential layer
- frontend report export controls

## Priority 3 — Long Term

### 7. Distributed Pipeline Execution

**Rationale**

The current deployment model is single-machine and suitable for an MSc-scale artefact. Larger evidence volumes and concurrent investigations would benefit from distributed execution.

**Implementation Approach**

- replace or supplement in-process job execution with Celery workers
- use Redis as the message broker
- separate acquisition/parsing/triage/reporting tasks across workers
- add worker-aware monitoring and retry logic

**Estimated Effort**

High

**Dependencies on Current Architecture**

- `JobManager`
- `JobRunner`
- pipeline stage boundaries
- monitoring and logging framework
- production deployment stack under `deploy/`

### 8. YARA Rule Integration

**Rationale**

YARA integration would add signature-based malware identification to complement current behavioural and heuristic analysis.

**Implementation Approach**

- add `yara-python` integration
- create a YARA scanning service and rule repository
- expose rule matches as normalized artefacts or enriched metadata
- add administrative rule management UI and reporting support

**Estimated Effort**

Medium

**Dependencies on Current Architecture**

- parser and processing extension points
- triage scoring
- report export layer
- admin settings / management pages

### 9. Case Collaboration

**Rationale**

Current case support includes multi-investigator assignment, but not real-time collaborative editing or concurrent analytical workflows. Collaboration would better support team-based investigations.

**Implementation Approach**

- add WebSocket collaboration channels
- introduce shared-presence and live-case activity streams
- support collaborative notes, assignments, and synchronized review state
- use conflict-control mechanisms such as operational transforms or CRDT-style patterns for shared text/comment objects

**Estimated Effort**

High

**Dependencies on Current Architecture**

- case lifecycle services
- user and RBAC layers
- WebSocket infrastructure from the real-time dashboard enhancement
- audit logging for collaborative actions

## Priority Justification

### Why Priority 1 First

Priority 1 items directly address the strongest current research and scope limitations:
- model quality limitation from Sharma et al. (2025)
- missing packet-level network analysis
- polling-based UX constraints in the current interface

They also fit naturally into existing extension points without requiring a full architectural rewrite.

### Why Priority 2 Next

Priority 2 items expand the platform's breadth and analytical sophistication but depend on a stable core:
- cloud evidence broadens scope
- anomaly detection deepens analysis
- multi-language reports improve accessibility

### Why Priority 3 Later

Priority 3 items are strategically valuable but structurally larger:
- distributed execution changes the operational model
- YARA adds a substantial signature-management concern
- real-time case collaboration changes both backend state management and frontend interaction design

## Recommended Next-Step Sequence

If only one enhancement is pursued next, the strongest recommendation is:

1. **ForensicLLM Fine-Tuning**
2. **Network Packet Analysis**
3. **Real-Time Dashboard Updates**

That sequence best matches the dissertation's current limitations, preserves architectural continuity, and creates the clearest path for follow-on publishable research.
