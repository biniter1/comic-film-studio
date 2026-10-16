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

test("phase 2a: analyze → line anchored to previous scene → edit, speaker, review, approve", async ({
  page,
  request,
}) => {
  const { pid, cid } = await approvedChapter(request);

  await page.goto(`/chapters/${cid}/frames`);
  await page.getByTestId("to-dialogue").click();
  await expect(page.getByRole("heading", { name: /Kịch bản thoại · Chương 7/ })).toBeVisible();

  await page.getByTestId("analyze-btn").click();
  const rows = page.getByTestId("line-row");
  await expect(rows).toHaveCount(3, { timeout: 30_000 });
  await expect(page.getByText("Thoại: bản nháp")).toBeVisible();

  // frame 2 is dialogue-only → its line is attached to frame #1
  const types = page.getByTestId("frame-type");
  await expect(types.nth(1)).toHaveValue("dialogue_only");
  await expect(rows.nth(1).getByTestId("anchor-select").locator("option:checked")).toHaveText("khung #1");

  // AI polish visible next to the raw text
  await expect(rows.nth(0).getByTestId("line-text")).toHaveValue("Câu thoại khung 1!");
  await expect(rows.nth(0).getByTestId("raw-text")).toHaveText("Câu thoại khung 1.");

  // approve is blocked while a low-confidence line is unreviewed
  await expect(page.getByTestId("approve-dialogue")).toBeDisabled();

  // edit a line (Enter saves)
  const t = rows.nth(2).getByTestId("line-text");
  await t.fill("Ngươi đứng lại cho ta!");
  await t.press("Enter");
  await expect(rows.nth(2).getByText("bạn sửa")).toBeVisible();

  // fix the speaker of the uncertain line → counts as reviewed
  await rows.nth(1).getByTestId("speaker-select").selectOption("lam_phong");
  await expect(rows.nth(1).getByTestId("mark-reviewed")).toHaveCount(0);
  await page.screenshot({ path: "e2e/screenshots/dialogue.png", fullPage: false });

  await page.getByTestId("approve-dialogue").click();
  await expect(page.getByText("Thoại: đã duyệt")).toBeVisible();

  // persisted
  await page.reload();
  await expect(page.getByTestId("line-row").nth(2).getByTestId("line-text")).toHaveValue("Ngươi đứng lại cho ta!");

  // glossary screen: AI suggestion, approve it; characters tab lists Lâm Phong
  await page.goto(`/projects/${pid}/glossary`);
  const term = page.getByTestId("term-row").first();
  await expect(term.getByText("AI đề xuất")).toBeVisible();
  await term.getByTestId("approve-item").click();
  await expect(term.getByText("Đã duyệt")).toBeVisible();
  await page.getByTestId("tab-characters").click();
  await expect(page.getByTestId("character-row")).toHaveCount(1);
  await page.screenshot({ path: "e2e/screenshots/glossary.png", fullPage: false });
});

test("phase 2a: manual mode — bundle download + paste with validation error", async ({ page, request }) => {
  const { cid } = await approvedChapter(request);
  await page.goto(`/chapters/${cid}/dialogue`);
  await page.getByRole("button", { name: "Chế độ thủ công" }).click();
  await page.getByTestId("manual-prepare").click();
  const unit = page.getByTestId("paste-unit");
  await expect(unit).toHaveCount(1);

  const dl = page.waitForEvent("download");
  await unit.getByText("Tải gói").click();
  expect((await dl).suggestedFilename()).toMatch(/^read_01\.zip$/);

  await unit.getByTestId("paste-text").fill('{"frames": []}');
  await unit.getByRole("button", { name: "Dán kết quả" }).click();
  await expect(page.getByText("Kết quả dán vào chưa đúng định dạng")).toBeVisible();
});
