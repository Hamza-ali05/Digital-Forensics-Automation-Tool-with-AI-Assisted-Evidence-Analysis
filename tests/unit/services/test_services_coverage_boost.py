"""Coverage boost for application services using AsyncMock dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.case_management.enums import CaseStatus, CustodyAction, EvidenceStatus
from dfat.case_management.exceptions import (
    CaseAlreadyClosedError,
    CaseError,
    CaseNotFoundError,
)
from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import EvidenceNotFoundError, GroundTruthNotFoundError, ParsingError
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import PipelineState
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.evidence_management.exceptions import EvidenceValidationError, InvalidEvidenceTransitionError
from dfat.evidence_management.models import EvidenceStatusChange, HashSet
from dfat.pipeline.enums import JobStatus
from dfat.services.analysis_service import AnalysisService
from dfat.services.case_service import CaseService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_management_service import EvidenceManagementService
from dfat.services.report_service import ReportService


def _case(status: CaseStatus = CaseStatus.OPEN, *, evidence_ids=None) -> Case:
    inv = CaseInvestigator(
        user_id="u1", username="alice", full_name="Alice", role="lead"
    )
    case = Case(
        metadata=CaseMetadata(case_id="c1", case_name="Case", investigator="Alice"),
        status=status,
        investigators=[inv],
        lead_investigator_id="u1",
    )
    if evidence_ids is not None:
        case.evidence_ids = list(evidence_ids)
    return case


def _report() -> ForensicReport:
    case = CaseMetadata(case_id="c1", case_name="C", investigator="I")
    return ForensicReport(
        report_id="rep-1",
        case=case,
        json_report=JSONReport(
            report_id="j1",
            evidence_id="ev-1",
            artefact_data=[],
            integrity_hash="b" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="n1",
            evidence_id="ev-1",
            summary_text="text",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=1.0,
    )


def _mgmt_service() -> tuple[EvidenceManagementService, dict]:
    deps = {
        name: MagicMock()
        for name in (
            "evidence_service",
            "validation_service",
            "hash_service",
            "custody_service",
            "metadata_repo",
            "status_repo",
            "evidence_repo",
            "case_repo",
            "audit_service",
        )
    }
    for dep in deps.values():
        for attr in (
            "get",
            "get_evidence",
            "list_all",
            "get_metadata",
            "get_hash_set",
            "get_current_status",
            "get_history",
            "get_custody_chain",
            "add_status_change",
            "save_metadata",
            "log_action",
            "record_access",
            "revalidate_evidence",
            "compute_hash_set",
            "verify_hash_set",
        ):
            setattr(deps[list(deps.keys())[0] if False else "evidence_service"], attr, AsyncMock())
    # properly AsyncMock key methods
    deps["evidence_service"].get_evidence = AsyncMock()
    deps["evidence_service"].register_evidence = AsyncMock()
    deps["validation_service"].validate_evidence = AsyncMock()
    deps["validation_service"].revalidate_evidence = AsyncMock()
    deps["hash_service"].compute_hash_set = MagicMock()
    deps["hash_service"].verify_hash_set = MagicMock()
    deps["custody_service"].get_custody_chain = AsyncMock(return_value=[])
    deps["custody_service"].record_access = AsyncMock(return_value=MagicMock())
    deps["custody_service"].record_acquisition = AsyncMock()
    deps["metadata_repo"].get_metadata = AsyncMock(return_value=None)
    deps["metadata_repo"].get_by_evidence_ids = AsyncMock(return_value={})
    deps["metadata_repo"].get_hash_set = AsyncMock(return_value=None)
    deps["metadata_repo"].save_metadata = AsyncMock()
    deps["status_repo"].get_current_status = AsyncMock(return_value=EvidenceStatus.REGISTERED)
    deps["status_repo"].get_current_statuses = AsyncMock(return_value={})
    deps["status_repo"].get_history = AsyncMock(return_value=[])
    deps["status_repo"].add_status_change = AsyncMock()
    deps["evidence_repo"].get = AsyncMock()
    deps["evidence_repo"].list_all = AsyncMock(return_value=[])
    deps["evidence_repo"].get_by_case = AsyncMock(return_value=[])
    deps["evidence_repo"].get_by_ids = AsyncMock(return_value={})
    deps["case_repo"].get = AsyncMock()
    deps["case_repo"].add_evidence_id = AsyncMock()
    deps["audit_service"].log_action = AsyncMock()
    deps["custody_service"].get_custody_chains = AsyncMock(return_value={})
    service = EvidenceManagementService(
        evidence_service=deps["evidence_service"],
        validation_service=deps["validation_service"],
        hash_service=deps["hash_service"],
        custody_service=deps["custody_service"],
        metadata_repo=deps["metadata_repo"],
        status_repo=deps["status_repo"],
        evidence_repo=deps["evidence_repo"],
        case_repo=deps["case_repo"],
        audit_service=deps["audit_service"],
    )
    return service, deps


# --- CaseService ---


@pytest.mark.asyncio
async def test_case_service_create_list_summary_archive() -> None:
    case_repo = AsyncMock()
    evidence_repo = AsyncMock()
    user_repo = AsyncMock()
    user_repo.get = AsyncMock(
        return_value=MagicMock(id="u1", username="alice", full_name="Alice")
    )
    created = _case(CaseStatus.CREATED)
    case_repo.save = AsyncMock(return_value="c1")
    case_repo.get = AsyncMock(return_value=created)
    case_repo.list_all = AsyncMock(return_value=[created])
    case_repo.search = AsyncMock(return_value=[created])
    case_repo.list_visible = AsyncMock(return_value=[created])
    case_repo.get_by_status = AsyncMock(return_value=[created])
    case_repo.get_by_investigator = AsyncMock(return_value=[created])
    case_repo.update_status = AsyncMock(return_value=_case(CaseStatus.ARCHIVED))
    case_repo.add_evidence_id = AsyncMock()
    case_repo.remove_investigator = AsyncMock(return_value=True)
    case_repo.add_investigator = AsyncMock()

    service = CaseService(
        case_repo=case_repo,
        evidence_repo=evidence_repo,
        user_repo=user_repo,
        audit_service=AsyncMock(),
        custody_service=AsyncMock(),
    )

    out = await service.create_case("Name", "desc", "u1")
    assert out.case_id == "c1"
    assert await service.list_cases() == [created]
    assert await service.list_cases(CaseStatus.CREATED) == [created]
    assert await service.get_my_cases("u1") == [created]
    assert await service.get_case("c1") == created

    # summary with missing + present evidence
    created.evidence_ids = ["ev-missing", "ev-1"]
    evidence_repo.get = AsyncMock(
        side_effect=[
            None,
            MagicMock(
                evidence_id="ev-1",
                file_path="/e.dd",
                evidence_type=EvidenceType.DISK_IMAGE,
                original_hash="a" * 64,
                file_size_bytes=1,
            ),
        ]
    )
    custody = AsyncMock()
    custody.get_custody_chain = AsyncMock(
        return_value=[MagicMock(action=CustodyAction.ACQUIRED)]
    )
    service._custody_service = custody
    summary = await service.get_case_summary("c1")
    assert summary["case_id"] == "c1"
    assert any(item.get("missing") for item in summary["evidence_summaries"])

    # remove investigator
    await service.remove_investigator("c1", "u2", "u1")

    # add evidence with empty custody chain
    open_case = _case(CaseStatus.OPEN)
    case_repo.get = AsyncMock(return_value=open_case)
    evidence_repo.get = AsyncMock(
        return_value=MagicMock(file_path="/e.dd", evidence_id="ev-1")
    )
    custody.get_custody_chain = AsyncMock(return_value=[])
    custody.record_acquisition = AsyncMock()
    await service.add_evidence_to_case("c1", "ev-1", "u1")

    with pytest.raises(CaseError):
        await service.assign_investigator("c1", "u2", "boss", "u1")

    closed = _case(CaseStatus.CLOSED)
    case_repo.get = AsyncMock(return_value=closed)
    with pytest.raises(CaseAlreadyClosedError):
        await service.assign_investigator("c1", "u2", "member", "u1")
    with pytest.raises(CaseAlreadyClosedError):
        await service.add_evidence_to_case("c1", "ev-1", "u1")

    case_repo.get = AsyncMock(return_value=open_case)
    evidence_repo.get = AsyncMock(return_value=None)
    with pytest.raises(CaseError, match="Evidence not found"):
        await service.add_evidence_to_case("c1", "ev-x", "u1")

    case_repo.get = AsyncMock(return_value=None)
    with pytest.raises(CaseNotFoundError):
        await service.get_case("missing")

    # archive
    closed_case = _case(CaseStatus.CLOSED, evidence_ids=["ev-1"])
    archived = _case(CaseStatus.ARCHIVED, evidence_ids=["ev-1"])
    case_repo.get = AsyncMock(side_effect=[closed_case, archived])
    case_repo.update_status = AsyncMock(return_value=archived)
    evidence_repo.get = AsyncMock(return_value=MagicMock(evidence_id="ev-1", file_path="/e"))
    custody.record_seal = AsyncMock()
    result = await service.archive_case("c1", "u1")
    assert result.status is CaseStatus.ARCHIVED


# --- EvidenceManagementService ---


@pytest.mark.asyncio
async def test_evidence_mgmt_detail_inventory_verify_transition_stats(
    sample_evidence_image: EvidenceImage,
    sample_case: Case,
) -> None:
    service, deps = _mgmt_service()
    sample_case.status = CaseStatus.OPEN
    sample_case.evidence_ids = [sample_evidence_image.evidence_id]

    deps["evidence_service"].get_evidence = AsyncMock(return_value=sample_evidence_image)
    deps["evidence_repo"].get = AsyncMock(return_value=sample_evidence_image)
    deps["evidence_repo"].list_all = AsyncMock(return_value=[sample_evidence_image])
    deps["evidence_repo"].get_by_case = AsyncMock(return_value=[sample_evidence_image])
    deps["case_repo"].get = AsyncMock(return_value=sample_case)
    deps["metadata_repo"].get_metadata = AsyncMock(return_value=None)
    deps["metadata_repo"].get_hash_set = AsyncMock(return_value=None)
    deps["status_repo"].get_current_status = AsyncMock(return_value=EvidenceStatus.REGISTERED)
    deps["status_repo"].get_history = AsyncMock(return_value=[])
    deps["custody_service"].get_custody_chain = AsyncMock(return_value=[])
    deps["hash_service"].compute_hash_set = MagicMock(
        return_value=HashSet(
            md5="0" * 32,
            sha1="1" * 40,
            sha256=sample_evidence_image.original_hash,
            file_size_bytes=sample_evidence_image.file_size_bytes,
        )
    )

    detail = await service.get_evidence_detail(sample_evidence_image.evidence_id)
    assert detail["evidence_id"] == sample_evidence_image.evidence_id
    assert "custody_chain" in detail

    inventory = await service.get_evidence_inventory()
    assert len(inventory) == 1
    by_case = await service.get_evidence_inventory(case_id=sample_case.case_id)
    assert len(by_case) == 1

    deps["case_repo"].get = AsyncMock(return_value=None)
    with pytest.raises(CaseNotFoundError):
        await service.get_evidence_inventory(case_id="missing")

    deps["case_repo"].get = AsyncMock(return_value=sample_case)
    verified = await service.verify_evidence(
        sample_evidence_image.evidence_id, "u1", "Alice"
    )
    assert verified["integrity_verified"] is True

    # fail verify path
    deps["hash_service"].compute_hash_set = MagicMock(
        return_value=HashSet(
            md5="0" * 32,
            sha1="1" * 40,
            sha256="f" * 64,
            file_size_bytes=1,
        )
    )
    failed = await service.verify_evidence(
        sample_evidence_image.evidence_id, "u1", "Alice"
    )
    assert failed["integrity_verified"] is False

    # stored hash set verify success
    stored = HashSet(
        md5="0" * 32,
        sha1="1" * 40,
        sha256=sample_evidence_image.original_hash,
        file_size_bytes=1,
    )
    deps["metadata_repo"].get_hash_set = AsyncMock(return_value=stored)
    deps["hash_service"].verify_hash_set = MagicMock(return_value=True)
    ok = await service.verify_evidence(sample_evidence_image.evidence_id, "u1", "Alice")
    assert ok["integrity_verified"] is True

    change = await service.transition_evidence_status(
        sample_evidence_image.evidence_id,
        EvidenceStatus.VALIDATING,
        "u1",
        "ok",
    )
    assert change.new_status is EvidenceStatus.VALIDATING

    deps["status_repo"].get_current_status = AsyncMock(
        return_value=EvidenceStatus.ARCHIVED
    )
    with pytest.raises(InvalidEvidenceTransitionError):
        await service.transition_evidence_status(
            sample_evidence_image.evidence_id,
            EvidenceStatus.PROCESSING,
            "u1",
            "bad",
        )

    deps["evidence_repo"].get = AsyncMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.transition_evidence_status(
            "missing", EvidenceStatus.VALIDATING, "u1", "x"
        )

    deps["evidence_repo"].get = AsyncMock(return_value=sample_evidence_image)
    deps["status_repo"].get_current_status = AsyncMock(return_value=EvidenceStatus.REGISTERED)
    await service.quarantine_evidence(sample_evidence_image.evidence_id, "u1", "unsafe")

    history = await service.get_status_history(sample_evidence_image.evidence_id)
    assert history == []

    stats = await service.get_evidence_statistics()
    assert stats["total"] >= 1

    deps["evidence_service"].get_evidence = AsyncMock(return_value=sample_evidence_image)
    deps["validation_service"].revalidate_evidence = AsyncMock(
        side_effect=EvidenceValidationError("bad", validation_failures=["x"])
    )
    soft = await service.validate_evidence(sample_evidence_image.evidence_id, "u1")
    assert soft["validation_passed"] is False


# --- ReportService ---


@pytest.mark.asyncio
async def test_report_service_exports_and_helpers(tmp_path: Path) -> None:
    report = _report()
    report_repo = AsyncMock()
    report_repo.get = AsyncMock(return_value=report)
    case_repo = AsyncMock()
    case_repo.get = AsyncMock(return_value=None)
    evidence_repo = AsyncMock()
    evidence_repo.get = AsyncMock(return_value=MagicMock(file_path=tmp_path / "e.dd"))

    pdf = MagicMock()
    pdf.export = MagicMock(return_value=tmp_path / "out.pdf")
    html = MagicMock()
    html.export = MagicMock(return_value=tmp_path / "out.html")
    json_exp = MagicMock()
    json_exp.export = MagicMock(return_value=tmp_path / "out.json")
    integrity = MagicMock()
    integrity.verify_report = MagicMock(return_value=MagicMock(valid=True))
    repro = MagicMock()
    repro.compare_reports = MagicMock(return_value=MagicMock(match=True))
    custody_gen = AsyncMock()
    custody_gen.generate = AsyncMock(return_value=MagicMock())
    audit_gen = AsyncMock()
    audit_gen.generate = AsyncMock(return_value=MagicMock())

    service = ReportService(
        report_repo=report_repo,
        audit_repo=AsyncMock(),
        pdf_exporter=pdf,
        html_exporter=html,
        json_file_exporter=json_exp,
        integrity_verifier=integrity,
        reproducibility_verifier=repro,
        custody_report_generator=custody_gen,
        audit_report_generator=audit_gen,
        case_repo=case_repo,
        evidence_repo=evidence_repo,
        export_dir=tmp_path,
    )

    assert (await service.export_pdf("rep-1")).name == "out.pdf"
    assert (await service.export_html("rep-1")).name == "out.html"
    assert (await service.export_json_file("rep-1")).name == "out.json"
    assert await service.verify_integrity("rep-1")
    assert await service.compare_reports("rep-1", "rep-1")
    assert await service.get_custody_report("rep-1")
    assert await service.get_audit_trail_report("rep-1")

    report_repo.get = AsyncMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.get_report("missing")


# --- AnalysisService ---


@pytest.mark.asyncio
async def test_analysis_service_full_triage_and_errors(
    sample_evidence_image: EvidenceImage,
    sample_artefact_set: ArtefactSet,
) -> None:
    report = _report()
    evidence_repo = AsyncMock()
    evidence_repo.get = AsyncMock(return_value=sample_evidence_image)
    artefact_repo = AsyncMock()
    report_repo = AsyncMock()
    audit_repo = AsyncMock(get_latest_entry_number=AsyncMock(return_value=0))
    integrity = MagicMock()
    integrity.verify_integrity = MagicMock(return_value=True)
    pipeline = MagicMock()
    job = MagicMock(status=JobStatus.COMPLETED, job_id="job-1", error_message=None)
    pipeline.execute_pipeline = AsyncMock(return_value=job)
    pipeline.get_job_report = MagicMock(return_value=report)
    pipeline.get_job_artefact_set = MagicMock(return_value=sample_artefact_set)
    pipeline._artefact_cache = {}
    state = PipelineState(
        case=sample_evidence_image.case,
        current_stage=PipelineStage.AI_TRIAGE,
    )
    pipeline.get_pipeline_state = MagicMock(return_value=state)

    service = AnalysisService(
        pipeline_orchestrator=pipeline,
        evidence_repo=evidence_repo,
        artefact_repo=artefact_repo,
        report_repo=report_repo,
        audit_repo=audit_repo,
        integrity_checker=integrity,
    )

    out = await service.run_full_analysis(sample_evidence_image.evidence_id, "u1")
    assert out.report_id == "rep-1"

    # no artefact set from pipeline still succeeds with empty set
    pipeline.get_job_artefact_set = MagicMock(return_value=None)
    await service.run_full_analysis(sample_evidence_image.evidence_id, "u1")

    pipeline.get_job_report = MagicMock(return_value=None)
    with pytest.raises(ParsingError, match="without a report"):
        await service.run_full_analysis(sample_evidence_image.evidence_id, "u1")

    job_fail = MagicMock(status=JobStatus.FAILED, job_id="j", error_message="x")
    pipeline.execute_pipeline = AsyncMock(return_value=job_fail)
    pipeline.get_job_report = MagicMock(return_value=report)
    with pytest.raises(ParsingError, match="failed"):
        await service.run_full_analysis(sample_evidence_image.evidence_id, "u1")

    pipeline.execute_pipeline = AsyncMock(return_value=job)
    pipeline.get_job_artefact_set = MagicMock(return_value=None)
    with pytest.raises(ParsingError, match="without artefacts"):
        await service.run_parse_only(sample_evidence_image.evidence_id, "u1")

    pipeline.get_job_artefact_set = MagicMock(return_value=sample_artefact_set)
    pipeline._artefact_cache = {}
    triage_state = await service.run_triage_only(sample_evidence_image.evidence_id, "u1")
    assert triage_state.current_stage is PipelineStage.AI_TRIAGE

    pipeline.get_pipeline_state = MagicMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.run_triage_only(sample_evidence_image.evidence_id, "u1")
    with pytest.raises(EvidenceNotFoundError):
        await service.get_analysis_status("missing")

    evidence_repo.get = AsyncMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.run_full_analysis("missing", "u1")


# --- EvaluationService ---


@pytest.mark.asyncio
async def test_evaluation_service_paths(sample_artefact_set: ArtefactSet) -> None:
    result = BenchmarkResult(
        benchmark_id="b1",
        dataset_name="dfrws",
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        time_to_triage_seconds=1.0,
        artefacts_expected=1,
        artefacts_recovered=1,
        false_positives=0,
        false_negatives=0,
    )
    response = UsabilityResponse(
        response_id="u1",
        participant_id="p1",
        usefulness_rating=5,
        accuracy_rating=5,
        clarity_rating=4,
    )
    ground = MagicMock()
    ground.dataset_name = "dfrws"
    loader = MagicMock()
    loader.load = MagicMock(return_value=ground)
    loader.load_dfrws = MagicMock(return_value=ground)
    loader.load_cfreds = MagicMock(return_value=ground)
    loader.list_all_datasets = MagicMock(return_value={"dfrws": ["a"], "cfreds": []})
    comparator = AsyncMock()
    comparator.compare = AsyncMock(return_value=result)
    artefact_repo = AsyncMock()
    artefact_repo.get = AsyncMock(return_value=sample_artefact_set)
    bench_repo = AsyncMock()
    bench_repo.list_all = AsyncMock(return_value=[result])
    bench_repo.get = AsyncMock(return_value=result)
    use_repo = AsyncMock()
    use_repo.save = AsyncMock(return_value="u1")
    use_repo.get_all_responses = AsyncMock(return_value=[response])
    collector = AsyncMock()
    collector.collect_response = AsyncMock(return_value="u1")
    collector.export_responses_anonymised = AsyncMock(return_value="[]")
    collector.delete_all_responses = AsyncMock(return_value=1)
    perf = MagicMock()
    perf.get_historical_results = AsyncMock(return_value=[result])
    perf.generate_performance_report = MagicMock(return_value=MagicMock())

    service = EvaluationService(
        benchmark_repo=bench_repo,
        usability_repo=use_repo,
        benchmark_comparator=comparator,
        ground_truth_loader=loader,
        audit_repo=AsyncMock(),
        artefact_repo=artefact_repo,
        response_collector=collector,
        performance_analyzer=perf,
    )

    now = datetime.now(UTC)
    assert await service.run_benchmark(
        "ev", "gt.json", "dfrws", sample_artefact_set, now, now, "u1"
    )
    assert await service.run_benchmark_for_dataset("ev", "ds", "dfrws", "u1")
    assert await service.run_benchmark_for_dataset(
        "ev", "ds", "cfreds", "u1", ground_truth_path="gt.json"
    )
    with pytest.raises(GroundTruthNotFoundError):
        await service.run_benchmark_for_dataset("ev", "ds", "unknown", "u1")
    artefact_repo.get = AsyncMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.run_benchmark_for_dataset("ev", "ds", "dfrws", "u1")

    artefact_repo.get = AsyncMock(return_value=sample_artefact_set)
    assert await service.submit_usability_response(response) == "u1"
    assert await service.collect_usability_response({"usefulness": 5}) == "u1"
    assert await service.get_benchmark_results()
    assert await service.get_benchmark_result("b1")
    bench_repo.get = AsyncMock(return_value=None)
    with pytest.raises(EvidenceNotFoundError):
        await service.get_benchmark_result("missing")
    assert await service.get_performance_report("dfrws")
    assert service.list_datasets()["dfrws"] == ["a"]
    instrument = service.get_questionnaire_instrument()
    assert "questions" in instrument
    analysis = await service.get_usability_analysis()
    assert isinstance(analysis, dict)
    assert await service.export_usability_responses() == "[]"
    assert await service.delete_usability_responses() == 1
