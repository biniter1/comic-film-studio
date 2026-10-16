import { expect, test } from "@playwright/test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

test("phase 1: project → chapter → import folder → auto frames → merge → save → approve", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dự án" })).toBeVisible();

  // create project
  await page.getByPlaceholder("Tên bộ truyện…").fill("Truyện E2E");
  await page.getByRole("button", { name: "Tạo dự án" }).click();
  await expect(page.getByRole("heading", { name: "Truyện E2E" })).toBeVisible();

  // create chapter → lands on the import screen
  await page.getByPlaceholder("Tên chapter (vd: Chương 1)…").fill("Chương 1");
  await page.getByRole("button", { name: "Thêm chapter" }).click();
  await expect(page.getByRole("heading", { name: /Nhập chapter · Chương 1/ })).toBeVisible();

  // import two pages from "folder"
  await page.getByTestId("file-input").setInputFiles([join(fixtures, "001.png"), join(fixtures, "002.png")]);
  await expect(page.getByTestId("page-grid").locator("> div")).toHaveCount(2, { timeout: 20_000 });
  await page.screenshot({ path: "e2e/screenshots/import.png", fullPage: true });

  // stitch & cut → navigates to frames
  await page.getByRole("button", { name: "Ghép & cắt khung" }).click();
  await expect(page.getByRole("heading", { name: /Khung · Chương 1/ })).toBeVisible({ timeout: 20_000 });
  const boxes = page.getByTestId("frame-box");
  await expect(boxes).toHaveCount(3); // panel split across the 2 pages is reassembled

  // merge frames 1+2, save, approve
  await page.getByTestId("merge-btn").first().click();
  await expect(boxes).toHaveCount(2);
  await expect(page.getByText("chưa lưu").first()).toBeVisible();
  await page.getByRole("button", { name: /Lưu/ }).click();
  await expect(page.getByText("Chưa lưu")).toHaveCount(0, { timeout: 10_000 });
  await page.getByRole("button", { name: "Duyệt khung" }).click();
  await expect(page.getByText("Khung: đã duyệt")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/frames.png", fullPage: false });

  // persisted after reload
  await page.reload();
  await expect(page.getByTestId("frame-box")).toHaveCount(2);

  // split back with Alt+click in the middle of frame 1
  const first = page.getByTestId("frame-box").first();
  const bb = (await first.boundingBox())!;
  await page.keyboard.down("Alt");
  await first.click({ position: { x: bb.width / 2, y: bb.height / 2 } });
  await page.keyboard.up("Alt");
  await expect(page.getByTestId("frame-box")).toHaveCount(3);
  // undo
  await page.keyboard.press("Control+z");
  await expect(page.getByTestId("frame-box")).toHaveCount(2);
});
