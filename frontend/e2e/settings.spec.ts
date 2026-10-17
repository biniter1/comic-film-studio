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

test("settings: switch to OpenAI provider, save key, test hint, and delete", async ({ page }) => {
  await page.goto("/settings");
  await page.getByTestId("provider-openai-btn").click();
  const effortSelect = page.getByTestId("openai-reasoning-effort-select");
  await expect(effortSelect).toHaveValue("low");
  await effortSelect.selectOption("high");
  await expect(effortSelect).toHaveValue("high");

  const input = page.getByPlaceholder("sk-…");
  await input.fill("sk-revid-e2e-fake-key-5432");
  await input.press("Enter");
  await expect(page.getByText(/Đang dùng key …5432/)).toBeVisible();
  await expect(page.getByTestId("openai-key-msg")).toBeVisible({ timeout: 20_000 });
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Xóa key" }).click();
  await expect(page.getByText("Dán API Key cổng tương thích OpenAI:")).toBeVisible();
});

test("settings: analysis models and parameters can be edited and saved", async ({ page }) => {
  await page.goto("/settings");
  const visionInput = page.getByTestId("vision-model-input");
  await expect(visionInput).toBeVisible();
  await visionInput.fill("gemini-3.8-flash");

  const textInput = page.getByTestId("text-model-input");
  await expect(textInput).toBeVisible();
  await textInput.fill("gemini-pro-latest");

  const rpmInput = page.getByTestId("analysis-rpm-input");
  await rpmInput.fill("6");

  const batchInput = page.getByTestId("read-batch-size-input");
  await batchInput.fill("8");

  await page.getByRole("button", { name: "Lưu tham số" }).click();
  await expect(page.getByText("Đã lưu cài đặt thành công!")).toBeVisible();
});


