import { rest } from "msw";

import pipelineService from "services/pipeline.service";
import config from "config";
import { server } from "../../test-utils/msw/server";

const API = config.apiBaseUrl;

describe("pipeline.service", () => {
  test("test_run_sends_evidence_and_mode", async () => {
    let seenBody = null;
    server.use(
      rest.post(`${API}/pipeline/run`, async (req, res, ctx) => {
        seenBody = await req.json();
        return res(
          ctx.status(202),
          ctx.json({
            job_id: "job-1",
            evidence_id: seenBody.evidence_id,
            mode: seenBody.mode,
            status: "queued",
          })
        );
      })
    );

    const result = await pipelineService.run({
      evidence_id: "ev-1",
      mode: "full",
    });
    expect(seenBody).toEqual(
      expect.objectContaining({ evidence_id: "ev-1", mode: "full" })
    );
    expect(result.job_id).toBe("job-1");
  });

  test("test_getProgress_returns_percentage", async () => {
    let seenUrl = "";
    server.use(
      rest.get(`${API}/pipeline/:id/progress`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        return res(
          ctx.status(200),
          ctx.json({
            job_id: req.params.id,
            status: "running",
            percent_complete: 42,
            stages_completed: 2,
            stages_total: 5,
            current_stage: "parsing",
          })
        );
      })
    );

    const progress = await pipelineService.getProgress("job-9");
    expect(seenUrl.endsWith("/pipeline/job-9/progress")).toBe(true);
    expect(progress.percent_complete).toBe(42);
    expect(progress.stages_completed).toBe(2);
    expect(progress.stages_total).toBe(5);
  });

  test("test_cancel_calls_correct_endpoint", async () => {
    let seenUrl = "";
    server.use(
      rest.post(`${API}/pipeline/:id/cancel`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        return res(
          ctx.status(200),
          ctx.json({ job_id: req.params.id, status: "cancelled" })
        );
      })
    );

    const result = await pipelineService.cancel("job-3");
    expect(seenUrl.endsWith("/pipeline/job-3/cancel")).toBe(true);
    expect(result.status).toBe("cancelled");
  });
});
