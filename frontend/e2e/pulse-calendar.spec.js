import { test, expect } from "@playwright/test";
import { dates, timestamp } from "../src/data/mock/fixtures/history.js";

// Native date popups live outside the page DOM. Inspect Chromium's accessibility
// tree to assert that the real picker opened, rather than mocking showPicker.
async function pickerIsOpen(session) {
  const { nodes } = await session.send("Accessibility.getFullAXTree");
  return nodes.some((node) => node.role?.value === "grid");
}

for (const width of [1440, 390]) {
  for (const fullscreen of [false, true]) {
    test(`calendar opens across its hit area at ${width}px, fullscreen=${fullscreen}`, async ({
      page,
      context,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("/#/pulse");
      if (fullscreen) {
        await page
          .getByRole("button", { name: "펄스맵 전체화면", exact: true })
          .click();
        await page.getByRole("button", { name: "시간축 표시" }).click();
      }
      const calendar = page.getByLabel("캘린더에서 날짜 선택");
      const session = await context.newCDPSession(page);
      // Enable accessibility before opening a native popup so it is included.
      await session.send("Accessibility.enable");
      await session.send("Accessibility.getFullAXTree");
      await expect(calendar).toHaveValue(dates.at(-1));
      const button = page.locator(".pulse-timeline__calendar");
      await button.scrollIntoViewIfNeeded();
      const bounds = await button.boundingBox();

      // Stay inside the rounded corners of the visible button.
      for (const y of [4, bounds.height / 2, bounds.height - 4]) {
        for (const x of [4, bounds.width / 2, bounds.width - 4]) {
          await page.mouse.click(bounds.x + x, bounds.y + y);
          await expect
            .poll(() => pickerIsOpen(session), {
              message: `Picker should open at (${x}, ${y})`,
            })
            .toBe(true);
          await page.keyboard.press("Escape");
          await expect.poll(() => pickerIsOpen(session)).toBe(false);
        }
      }

      // Select a day through the real popup and verify that the map follows it.
      await calendar.click({ position: { x: 2, y: 2 } });
      await expect.poll(() => pickerIsOpen(session)).toBe(true);
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("Enter");
      await expect(calendar).toHaveValue(dates.at(-2));
      await expect(page.locator(".pulse-layout")).toHaveAttribute(
        "data-snapshot",
        timestamp(dates.at(-2)),
      );

      if (fullscreen) {
        await expect(
          page.getByRole("dialog", { name: "펄스맵 전체화면" }),
        ).toBeVisible();
      }
      await session.detach();
    });
  }
}
