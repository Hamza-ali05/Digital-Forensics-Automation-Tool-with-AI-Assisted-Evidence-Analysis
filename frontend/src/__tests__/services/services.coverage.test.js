/**
 * Coverage helpers for remaining service methods (mocked HTTP, no MSW).
 */
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import reportsService from "services/reports.service";
import auditService from "services/audit.service";
import aiService from "services/ai.service";
import healthService from "services/health.service";
import usersService from "services/users.service";
import evaluationService from "services/evaluation.service";
import * as api from "services/api";

jest.mock("services/api", () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPut: jest.fn(),
  apiDelete: jest.fn(),
  apiDownload: jest.fn(),
}));

describe("service method coverage (mocked api)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.URL.createObjectURL = jest.fn(() => "blob:mock");
    global.URL.revokeObjectURL = jest.fn();
    document.body.innerHTML = "";
  });

  test("covers_remaining_service_exports", async () => {
    api.apiGet.mockResolvedValue({ data: { ok: true, users: [], total: 0 } });
    api.apiPost.mockResolvedValue({ data: { ok: true } });
    api.apiPut.mockResolvedValue({ data: {} });
    api.apiDelete.mockResolvedValue({ data: {} });
    api.apiDownload.mockResolvedValue({
      data: { size: 1 },
      headers: { "content-disposition": 'attachment; filename="r.bin"' },
    });

    await healthService.check();
    await healthService.ready();
    await healthService.detailed();
    await usersService.getMe();
    await usersService.list();
    await usersService.getById("u1");
    await usersService.deactivate("u1");

    expect(aiService.isAiHealthy({ is_healthy: true })).toBe(true);
    expect(aiService.isAiHealthy({ healthy: true })).toBe(true);
    expect(aiService.isAiHealthy({ available: true })).toBe(true);
    expect(aiService.isAiHealthy({ status: "healthy" })).toBe(true);
    expect(aiService.isAiHealthy({})).toBe(false);
    await aiService.getHealth();
    await aiService.getStats();
    await aiService.classify({});
    await aiService.summarize({});
    await aiService.explain("a1");
    await aiService.ask({});
    await aiService.getCacheStats();
    await aiService.clearCache();

    api.apiGet.mockResolvedValueOnce({ data: { dfrws: [], cfreds: [] } });
    await evaluationService.getDatasets();
    await evaluationService.runBenchmark({});
    api.apiGet.mockResolvedValueOnce({ data: [{ id: 1 }] });
    await evaluationService.getResults();
    api.apiGet.mockResolvedValueOnce({ data: { results: [{ id: 2 }] } });
    await evaluationService.getResults();
    await evaluationService.getResult("b1");
    await evaluationService.getPerformance({});
    await evaluationService.getQuestionnaire();
    await evaluationService.submitQuestionnaire({});

    await casesService.getMine();
    await casesService.getSummary("c1");
    await casesService.assignInvestigator("c1", { user_id: "u2", role: "member" });
    await casesService.removeInvestigator("c1", "u2");
    await casesService.addEvidence("c1", { evidence_id: "ev-1" });

    await pipelineService.getById("j1");
    api.apiGet.mockResolvedValueOnce({ data: [{ job_id: "j1" }] });
    await pipelineService.listJobs();
    api.apiGet.mockResolvedValueOnce({ data: { jobs: [{ job_id: "j2" }] } });
    await pipelineService.listJobs();
    await pipelineService.listParsers();

    await evidenceService.getStatistics();
    await evidenceService.validate("ev-1");
    await evidenceService.getStatus("ev-1");
    await evidenceService.quarantine("ev-1", { reason: "x" });

    api.apiGet.mockResolvedValueOnce({
      data: {
        entries: [
          { entry_number: 1, action: "acquired", hash_at_action: "aa".repeat(32) },
          { entry_number: 2, action: "accessed", hash_at_action: "aa".repeat(32) },
        ],
      },
    });
    api.apiPost.mockResolvedValueOnce({ data: { integrity_verified: true } });
    const ok = await evidenceService.verifyCustody("ev-1");
    expect(ok.is_valid).toBe(true);

    api.apiGet.mockResolvedValueOnce({ data: { entries: [] } });
    const empty = await evidenceService.verifyCustody("ev-2");
    expect(empty.is_valid).toBe(false);

    await reportsService.getById("r1");
    await reportsService.getJson("r1");
    await reportsService.getNarrative("r1");
    await reportsService.verify("r1");
    await reportsService.getCustody("r1");
    await reportsService.getCustodyReport("r1");
    await reportsService.getAuditTrail("r1");
    await reportsService.compare({});
    await reportsService.exportPdf("r1");
    await reportsService.exportHtml("r1");
    await reportsService.exportJson("r1");

    api.apiGet.mockResolvedValueOnce({
      data: [
        { job_id: "j1", report_id: "r1" },
        { job_id: "j2", report_id: "r1" },
        { job_id: "j3" },
      ],
    });
    expect(await reportsService.getTotal()).toBe(1);

    api.apiGet
      .mockResolvedValueOnce({
        data: [{ job_id: "j1", report_id: "r1" }],
      })
      .mockResolvedValueOnce({
        data: {
          entries: [
            {
              entry_number: 1,
              timestamp: "2026-01-01T00:00:00Z",
              action: "X",
              details: { user_id: "u1" },
            },
          ],
        },
      });
    const aggregated = await auditService.listAggregated({ maxReports: 3 });
    expect(aggregated.length).toBe(1);

    api.apiGet.mockResolvedValueOnce({
      data: [{ action: "Y", timestamp: "2026-01-02T00:00:00Z" }],
    });
    expect(await auditService.getReportTrail("r1")).toHaveLength(1);
  });
});
