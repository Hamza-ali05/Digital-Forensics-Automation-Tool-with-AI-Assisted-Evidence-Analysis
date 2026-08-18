import { rest } from "msw";

import evidenceService from "services/evidence.service";
import config from "config";
import { server } from "../../test-utils/msw/server";

const API = config.apiBaseUrl;

describe("evidence.service", () => {
  test("test_register_sends_correct_payload", async () => {
    let seenBody = null;
    server.use(
      rest.post(`${API}/evidence/register`, async (req, res, ctx) => {
        seenBody = await req.json();
        return res(
          ctx.status(201),
          ctx.json({
            evidence_id: "ev-1",
            file_path: seenBody.file_path,
            status: "registered",
          })
        );
      })
    );

    const payload = {
      file_path: "/data/disk.E01",
      evidence_type: "disk_image",
      case_id: "c1",
      original_hash: "abc123",
    };
    const result = await evidenceService.register(payload);
    expect(seenBody).toEqual(payload);
    expect(result.evidence_id).toBe("ev-1");
  });

  test("test_getDetail_returns_full_metadata", async () => {
    let seenUrl = "";
    server.use(
      rest.get(`${API}/evidence/:id/detail`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        return res(
          ctx.status(200),
          ctx.json({
            evidence_id: req.params.id,
            file_path: "/data/disk.E01",
            metadata: {
              mime_type: "application/octet-stream",
              hash_set: {
                sha256: "deadbeef".repeat(8),
                md5: "d41d8cd98f00b204e9800998ecf8427e",
              },
            },
          })
        );
      })
    );

    const detail = await evidenceService.getDetail("ev-9");
    expect(seenUrl.endsWith("/evidence/ev-9/detail")).toBe(true);
    expect(detail.metadata.hash_set.sha256).toMatch(/^deadbeef/);
    expect(detail.metadata.mime_type).toBe("application/octet-stream");
  });

  test("test_verifyIntegrity_returns_hash_result", async () => {
    let seenUrl = "";
    server.use(
      rest.post(`${API}/evidence/:id/verify-integrity`, (req, res, ctx) => {
        seenUrl = req.url.pathname;
        return res(
          ctx.status(200),
          ctx.json({
            evidence_id: req.params.id,
            integrity_verified: true,
            hash_set: { sha256: "aa".repeat(32) },
            timestamp: "2026-01-01T00:00:00Z",
          })
        );
      })
    );

    const result = await evidenceService.verifyIntegrity("ev-1");
    expect(seenUrl.endsWith("/evidence/ev-1/verify-integrity")).toBe(true);
    expect(result.integrity_verified).toBe(true);
    expect(result.hash_set.sha256).toHaveLength(64);
  });

  test("test_getInventory_includes_filters", async () => {
    let seenParams = {};
    server.use(
      rest.get(`${API}/evidence/inventory`, (req, res, ctx) => {
        seenParams = Object.fromEntries(req.url.searchParams.entries());
        return res(
          ctx.status(200),
          ctx.json({
            items: [
              {
                evidence_id: "ev-1",
                case_id: "c1",
                file_name: "disk.E01",
                status: "processed",
              },
            ],
            total: 1,
          })
        );
      })
    );

    const inventory = await evidenceService.getInventory({
      case_id: "c1",
      status: "processed",
    });
    expect(seenParams).toEqual(
      expect.objectContaining({ case_id: "c1", status: "processed" })
    );
    expect(inventory.items[0].evidence_id).toBe("ev-1");
  });
});
