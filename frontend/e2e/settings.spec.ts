import { expect, test } from "@playwright/test";

test("settings: save Gemini key with Enter shows feedback, key hint, delete", async ({ page }) => {
  await page.goto("/settings");
  const input = page.getByPlaceholder("AIzaSy…");
  await input.fill("AIzaSyE2EFAKEKEYFAKEKEYFAKEKEY9876");
  await input.press("Enter");
  // saved → status flips and a message appears (connection test fails offline: still a clear message)
  await expect(page.getByText("Đã cấu hình")).toBeVisible();
  await expect(page.getByText(/Đang dùng key …9876/)).toBeVisible();
  await expect(page.getByTestId("key-msg")).toBeVisible({ timeout: 20_000 });
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Xóa key" }).click();
  await expect(page.getByText("Chưa cấu hình")).toBeVisible();
});
