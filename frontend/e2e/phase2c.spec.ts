import { APIRequestContext, expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

async function waitJob(api: APIRequestContext, id: string) {
  for (let i = 0; i < 200; i++) {
    const j = await (await api.get(`/api/jobs/${id}`)).json();
    if (["succeeded", "failed", "cancelled"].includes(j.status)) return j;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`job ${id} timeout`);
}

/** Project + chapter with 3 approved frames, set up through the API (UI covered by phase1.spec). */
async function approvedChapter(api: APIRequestContext) {
  const p = await (await api.post("/api/projects", { data: { name: "Truyện thoại" } })).json();
  const ch = await (await api.post(`/api/projects/${p.id}/chapters`, { data: { title: "Chương 7" } })).json();
  const files = ["001.png", "002.png"].map((n) => ({
    name: n,
    mimeType: "image/png",
    buffer: readFileSync(join(fixtures, n)),
  }));
  const up = await api.post(`/api/chapters/${ch.id}/import/files`, { multipart: { files: files[0] } });
  expect((await waitJob(api, (await up.json()).id)).status).toBe("succeeded");
  const up2 = await api.post(`/api/chapters/${ch.id}/import/files`, { multipart: { files: files[1] } });
  expect((await waitJob(api, (await up2.json()).id)).status).toBe("succeeded");
  const cut = await (await api.post(`/api/chapters/${ch.id}/frames/auto`)).json();
  expect((await waitJob(api, cut.id)).status).toBe("succeeded");
  expect((await api.post(`/api/chapters/${ch.id}/frames/approve`)).ok()).toBeTruthy();
  return { pid: p.id as string, cid: ch.id as string };
}

test("phase 2c: plan shots → storyboard cards → edit camera → approve plan", async ({ page, request }) => {
  const { cid } = await approvedChapter(request);
  // read + dialogue (fake), then approve the script through the API
  const r = await (await request.post(`/api/chapters/${cid}/analysis/read`, { data: { mode: "api" } })).json();
  for (const j of r.jobs) expect((await waitJob(request, j.id)).status).toBe("succeeded");
  await request.post(`/api/chapters/${cid}/dialogue/review-all`);
  expect((await request.post(`/api/chapters/${cid}/dialogue/approve`)).ok()).toBeTruthy();

  await page.goto(`/chapters/${cid}/dialogue`);
  await page.getByTestId("to-shots").click();
  await expect(page.getByRole("heading", { name: /Bảng shot/ })).toBeVisible();
  await page.getByTestId("plan-btn").click();
  const cards = page.getByTestId("shot-card");
  await expect(cards.first()).toBeVisible({ timeout: 30_000 });
  const n = await cards.count();
  expect(n).toBeGreaterThan(0);
  await expect(page.getByText("Shot: bản nháp")).toBeVisible();
  await expect(cards.first().getByTestId("beat-bar")).toContainText("wind moves his robe");

  // prompts are composed by the app
  await cards.first().getByText("Prompt video (Muse)").click();
  await expect(cards.first().getByTestId("prompt-text")).toContainText("Push in, slow, medium shot.");

  // edit camera movement → prompt recomposed
  await cards.first().getByTestId("edit-shot").click();
  await cards.first().getByTestId("shot-editor").locator("select").nth(2).selectOption("orbit_right");
  await cards.first().getByTestId("save-shot").click();
  await expect(cards.first().getByText("bạn sửa")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/shots.png", fullPage: false });

  await page.getByTestId("approve-plan").click();
  await expect(page.getByText("Kế hoạch shot: đã duyệt")).toBeVisible();
});
