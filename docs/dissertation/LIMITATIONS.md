# Limitations

This document records the principal limitations of the DFAT dissertation artefact. Each limitation is described honestly with its impact, mitigation, and future-work direction.

## 1. Base LLaMA-3 Rather Than a ForensicLLM

### Description
DFAT currently uses a base local LLaMA-3 model through Ollama rather than a forensic-domain fine-tuned model.

### Impact
- lower domain specificity
- risk of missed nuance in forensic artefacts
- residual hallucination risk despite prompt controls

### Mitigation
- local-only deployment
- anti-hallucination prompt rules
- `HallucinationGuard`
- rule-based fallback
- JSON primary record and narrative disclaimer

### Future Work
- fine-tune or replace the model with a forensic-specialised model
- evaluate prompt tuning against practitioner-labelled corpora

## 2. Public Datasets Rather Than Real-World Evidence

### Description
Evaluation is performed on DFRWS and CFReDS style public benchmark datasets rather than operational evidence from live cases.

### Impact
- limited ecological validity
- reduced exposure to messy, incomplete, and legally constrained evidence conditions

### Mitigation
- use recognised public benchmark families
- keep evaluation methodology explicit and reproducible

### Future Work
- ethically approved field evaluation with real organisational evidence under supervision

## 3. Simulated Investigators Rather Than Practising Experts

### Description
Usability evaluation is designed around anonymised questionnaire responses and can support simulated or student investigator cohorts.

### Impact
- practitioner realism may be limited
- usefulness findings may not generalise to expert examiners

### Mitigation
- fixed instrument versioning
- explicit comparison framing rather than overclaiming
- confidence intervals and sample-size caution in analysis

### Future Work
- larger sample with practising forensic investigators
- multi-site evaluation across academic and operational settings

## 4. MSc Timeframe Constraints

### Description
This artefact was developed within MSc project scope and time limits.

### Impact
- some advanced features remain out of scope
- operational hardening is present but not exhaustive
- evaluation breadth is necessarily constrained

### Mitigation
- prioritised DSR alignment
- explicit ADR trail
- verification scripts to demonstrate delivered scope

### Future Work
- extend evaluation depth
- broaden parser coverage
- add operational governance and deployment refinements

## 5. Network Analysis Is Not the Central Focus of This Iteration

### Description
DFAT includes memory-network artefact handling, but deep standalone network-forensics capability is not the main emphasis of this dissertation version.

### Impact
- limited coverage of packet-level, flow-level, and intrusion-centric network workflows

### Mitigation
- include network connection artefact extraction in the memory-analysis path
- preserve layered architecture so additional modules can be added cleanly

### Future Work
- packet capture ingestion
- DNS and flow reconstruction
- external threat-intelligence enrichment

## 6. Single-Machine Deployment

### Description
The current production model targets a single-machine deployment with local services.

### Impact
- limited horizontal scalability
- constrained concurrency for large workloads
- SQLite can become a bottleneck for multi-user write-heavy scenarios

### Mitigation
- production Docker orchestration
- health checks, backups, monitoring, and CI/CD
- explicit documentation of current deployment boundaries

### Future Work
- PostgreSQL-backed deployment
- distributed workers
- object storage and queue-backed scaling

## 7. Residual LLM Non-Determinism

### Description
Low-temperature inference improves stability but does not eliminate probabilistic variation.

### Impact
- narrative wording may differ between runs
- some classification details may vary even with identical inputs

### Mitigation
- low temperature (`0.1`)
- prompt version tracking
- cached responses
- JSON evidential layer as authoritative record

### Future Work
- stricter constrained decoding
- more caching and memoisation paths
- model-specific determinism studies

## 8. Dependency on Optional Forensic Libraries

### Description
Some parser capabilities depend on external libraries such as `pytsk3`, `Evtx`, `python-registry`, and Volatility3.

### Impact
- environment-specific capability gaps
- possible graceful degradation when dependencies are unavailable

### Mitigation
- parser availability probing
- lazy imports
- ADR-backed graceful degradation strategy

### Future Work
- containerised dependency pinning for all forensic backends
- automated environment capability reporting in UI and API

## 9. Academic Scope of the Evidence Claim

### Description
The dissertation can show that the tool implements and verifies research objectives, but it cannot claim universal operational superiority across all forensic contexts.

### Impact
- conclusions must remain appropriately bounded
- claims should be framed as evidence-supported within the tested scope

### Mitigation
- formal verification scripts
- benchmark methodology documentation
- explicit ethical and methodological transparency

### Future Work
- replicate the study in broader operational environments
- compare against additional baselines and datasets
