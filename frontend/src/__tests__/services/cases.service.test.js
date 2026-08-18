import { rest } from "msw";

import casesService from "services/cases.service";
import config from "config";
import { server } from "../../test-utils/msw/server";

const API = config.apiBaseUrl;

describe("cases.service", () => {
  test("test_list_calls_correct_endpoint", async () => {
    let seenUrl = "";
    let seenParams = {};
    server.use(
      rest.get(`${API}/cases`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        seenParams = Object.fromEntries(req.url.searchParams.entries());
        return res(
          ctx.status(200),
          ctx.json({
            cases: [{ case_id: "c1", case_name: "Alpha", status: "active" }],
            total: 1,
          })
        );
      })
    );

    const data = await casesService.list({ status: "active", limit: 10 });
    expect(seenUrl.endsWith("/cases")).toBe(true);
    expect(seenParams).toEqual(
      expect.objectContaining({ status: "active", limit: "10" })
    );
    expect(data.total).toBe(1);
    expect(data.cases[0].case_id).toBe("c1");
  });

  test("test_create_sends_correct_payload", async () => {
    let seenBody = null;
    server.use(
      rest.post(`${API}/cases`, async (req, res, ctx) => {
        seenBody = await req.json();
        return res(
          ctx.status(201),
          ctx.json({
            case_id: "c-new",
            case_name: seenBody.case_name,
            status: "created",
          })
        );
      })
    );

    const payload = {
      case_name: "New Case",
      description: "Investigation",
      priority: "high",
    };
    const created = await casesService.create(payload);
    expect(seenBody).toEqual(payload);
    expect(created.case_id).toBe("c-new");
    expect(created.status).toBe("created");
  });

  test("test_getById_includes_id_in_url", async () => {
    let seenUrl = "";
    server.use(
      rest.get(`${API}/cases/:id`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        return res(
          ctx.status(200),
          ctx.json({
            case_id: req.params.id,
            case_name: "Detail Case",
            status: "open",
          })
        );
      })
    );

    const detail = await casesService.getById("c42");
    expect(seenUrl.endsWith("/cases/c42")).toBe(true);
    expect(detail.case_id).toBe("c42");
    expect(detail.case_name).toBe("Detail Case");
  });

  test("test_lifecycle_methods_call_correct_endpoints", async () => {
    const hits = [];
    server.use(
      rest.post(`${API}/cases/:id/open`, (req, res, ctx) => {
        hits.push({ action: "open", path: req.url.pathname });
        return res(ctx.status(200), ctx.json({ case_id: req.params.id, status: "open" }));
      }),
      rest.post(`${API}/cases/:id/activate`, (req, res, ctx) => {
        hits.push({ action: "activate", path: req.url.pathname });
        return res(
          ctx.status(200),
          ctx.json({ case_id: req.params.id, status: "active" })
        );
      }),
      rest.post(`${API}/cases/:id/close`, async (req, res, ctx) => {
        const body = await req.json().catch(() => ({}));
        hits.push({ action: "close", path: req.url.pathname, body });
        return res(
          ctx.status(200),
          ctx.json({ case_id: req.params.id, status: "closed" })
        );
      }),
      rest.post(`${API}/cases/:id/archive`, (req, res, ctx) => {
        hits.push({ action: "archive", path: req.url.pathname });
        return res(
          ctx.status(200),
          ctx.json({ case_id: req.params.id, status: "archived" })
        );
      }),
      rest.post(`${API}/cases/:id/submit-review`, (req, res, ctx) => {
        hits.push({ action: "submitReview", path: req.url.pathname });
        return res(
          ctx.status(200),
          ctx.json({ case_id: req.params.id, status: "under_review" })
        );
      }),
      rest.post(`${API}/cases/:id/reopen`, async (req, res, ctx) => {
        const body = await req.json().catch(() => ({}));
        hits.push({ action: "reopen", path: req.url.pathname, body });
        return res(
          ctx.status(200),
          ctx.json({ case_id: req.params.id, status: "open" })
        );
      })
    );

    await casesService.open("c1");
    await casesService.activate("c1");
    await casesService.close("c1", { reason: "done" });
    await casesService.archive("c1");
    await casesService.submitReview("c1");
    await casesService.reopen("c1", { reason: "new lead" });

    expect(hits.map((h) => h.action)).toEqual([
      "open",
      "activate",
      "close",
      "archive",
      "submitReview",
      "reopen",
    ]);
    expect(hits.every((h) => h.path.includes("/cases/c1/"))).toBe(true);
    expect(hits.find((h) => h.action === "close").body).toEqual({
      reason: "done",
    });
    expect(hits.find((h) => h.action === "reopen").body).toEqual({
      reason: "new lead",
    });
  });
});
