import { APIRequestContext, expect, test } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const screenshots = join(dirname(fileURLToPath(import.meta.url)), "screenshots");

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
  const p = await (await api.post("/api/projects", { data: { name: "Truyện Bible" } })).json();
  const ch = await (await api.post(`/api/projects/${p.id}/chapters`, { data: { title: "Chương 1" } })).json();
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

test("phase 2b: character cards, look_lock, ref frames, sheet upload and approval", async ({
  page,
  request,
}) => {
  mkdirSync(screenshots, { recursive: true });
  const { pid, cid } = await approvedChapter(request);

  // Run analysis using scripted fake provider to extract characters and frame readings
  const an = await (
    await request.post(`/api/chapters/${cid}/analysis/read`, {
      data: { mode: "api", then_dialogue: true },
    })
  ).json();
  for (const j of an.jobs) {
    expect((await waitJob(request, j.id)).status).toBe("succeeded");
  }

  // Open Glossary page and go to Characters tab
  await page.goto(`/projects/${pid}/glossary`);
  await page.getByTestId("tab-characters").click();

  const charCard = page.getByTestId("character-row").first();
  await expect(charCard).toBeVisible();

  // 1. Cắt 1 vùng từ khung tham chiếu
  const cropBtn = charCard.getByTestId("crop-ref-btn");
  await cropBtn.click();

  const saveCropBtn = page.getByTestId("save-crop-btn");
  await expect(saveCropBtn).toBeVisible({ timeout: 10_000 });
  await saveCropBtn.click();

  // 2. Thấy ảnh tham chiếu xuất hiện
  const refItem = charCard.getByTestId("char-ref-item");
  await expect(refItem).toHaveCount(1, { timeout: 15_000 });

  // 3. Chạy AI hồ sơ (fake)
  const aiBtn = charCard.getByTestId("ai-look-profile-btn");
  await aiBtn.click();

  // Chờ bảng đề xuất hiện lên
  const applyLookBtn = charCard.getByTestId("apply-look-lock");
  await expect(applyLookBtn).toBeVisible({ timeout: 20_000 });

  // 4. Áp dụng look_lock
  await applyLookBtn.click();
  const lookInput = charCard.getByTestId("look-lock-input");
  await expect(lookInput).toHaveValue(/sharp red eyes/);

  // 5. Thả 1 ảnh sheet (dùng e2e/fixtures/001.png)
  const sheetInput = charCard.getByTestId("sheet-file-input");
  await sheetInput.setInputFiles(join(fixtures, "001.png"));

  // 6. Duyệt sheet
  const approveBtn = charCard.getByTestId("sheet-approve-btn");
  await expect(approveBtn).toBeVisible({ timeout: 15_000 });
  await approveBtn.click();

  // 7. Thấy "Đã duyệt"
  await expect(charCard.getByTestId("sheet-status")).toHaveText("Đã duyệt");

  // Chụp màn hình vào e2e/screenshots/bible.png
  await page.screenshot({ path: "e2e/screenshots/bible.png", fullPage: false });
});

