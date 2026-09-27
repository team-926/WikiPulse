import { test, expect } from "@playwright/test";
import { serve } from "./server.js";
import { mockClient } from "../src/data/mock/client.js";

const original = (await mockClient.getIssue("iran-hormuz-2025")).data;
const olderGroup = {
  id: 902,
  label: "오래된 해저 케이블 기록",
  source: "replay",
  status: "CONFIRMED",
  pulseScore: 12,
  snapshotTs: "2026-07-18T01:00:00Z",
  firstSeen: "2026-07-17T01:00:00Z",
  occurrenceCount: 4,
  defaultReportId: 901,
  summary: "이전 날짜에 저장된 리포트",
  memberCount: 2,
  stockCount: 1,
};

async function setup(page, groupsFor) {
  return serve(page, async ({ route, url }) => {
    if (url.pathname === "/api/v1/issues/history/groups") {
      const rows = groupsFor(url.searchParams.get("q") || "");
      if (rows === null) {
        await route.fulfill({
          status: 500,
          json: { error: { code: "INTERNAL" } },
        });
      } else {
        await route.fulfill({
          json: {
            data: rows,
            meta: {
              pagination: {
                offset: Number(url.searchParams.get("offset") || 0),
                limit: Number(url.searchParams.get("limit") || 20),
                total: rows.length,
                hasMore: false,
              },
            },
          },
        });
      }
      return true;
    }
    if (/^\/api\/v1\/issues\/(901|903)$/.test(url.pathname)) {
      await route.fulfill({
        json: {
          data: {
            ...original,
            id: Number(url.pathname.split("/").at(-1)),
            label: olderGroup.label,
            snapshotTs: olderGroup.firstSeen,
          },
        },
      });
      return true;
    }
    if (/^\/api\/v1\/issues\/(901|903)\/history\/reports$/.test(url.pathname)) {
      await route.fulfill({
        json: {
          data: [],
          meta: {
            pagination: {
              offset: 0,
              limit: 100,
              total: 0,
              hasMore: false,
            },
          },
        },
      });
      return true;
    }
    return false;
  });
}

test("네비바도 이슈 페이지와 같은 전체 기록을 검색하고 기본 리포트로 이동한다", async ({
  page,
}) => {
  const calls = await setup(page, (q) => (q === "해저" ? [olderGroup] : []));
  await page.goto("/#/issues");
  await page.getByRole("searchbox", { name: "사건 검색" }).fill("해저");
  const pageResult = page.locator(".event-row__title");
  await expect(pageResult).toContainText(olderGroup.label);
  await expect(pageResult).toHaveAttribute(
    "href",
    "#/issues/901?q=%ED%95%B4%EC%A0%80",
  );

  const search = page.getByRole("combobox", { name: "통합 검색" });
  await search.fill("  해저  ");
  const result = page.getByRole("option", { name: /오래된 해저 케이블 기록/ });
  await expect(result).toContainText("4개 기록");
  await expect(result).toHaveAttribute("href", "#/issues/901");
  const queries = calls.filter(
    (url) =>
      url.pathname === "/api/v1/issues/history/groups" &&
      url.searchParams.get("q") === "해저",
  );
  expect(queries.map((url) => url.searchParams.get("limit"))).toEqual([
    "20",
    "7",
  ]);
  expect(
    queries.every(
      (url) =>
        !url.searchParams.has("source") && !url.searchParams.has("snapshotTs"),
    ),
  ).toBe(true);
  expect(
    calls.some(
      (url) =>
        url.pathname === "/api/v1/issues" &&
        url.searchParams.get("limit") === "100",
    ),
  ).toBe(false);
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page).toHaveURL(/#\/issues\/901$/);
  await expect(search).toHaveValue("");
});

test("네비바는 이력 검색의 live와 replay 결과를 보여주고 기본 리포트가 없으면 대표 기록을 연다", async ({
  page,
}) => {
  const liveGroup = {
    ...olderGroup,
    id: 903,
    source: "live",
    label: "실시간 해저 케이블 기록",
    defaultReportId: null,
    occurrenceCount: 1,
  };
  await setup(page, (q) => (q === "해저" ? [olderGroup, liveGroup] : []));
  await page.goto("/#/issues");
  await page.getByRole("combobox", { name: "통합 검색" }).fill("해저");
  const results = page.getByRole("listbox").getByRole("option");
  await expect(results).toHaveCount(2);
  const liveResult = page.getByRole("option", {
    name: /실시간 해저 케이블 기록/,
  });
  await expect(liveResult).toHaveAttribute("href", "#/issues/903");
  await liveResult.click();
  await expect(page).toHaveURL(/#\/issues\/903$/);
});

test("전체 기록 검색 실패를 재시도하고 검색어를 지운 뒤 종목을 검색한다", async ({
  page,
}) => {
  let attempts = 0;
  await setup(page, (q) => {
    if (q !== "해저") return [];
    attempts += 1;
    return attempts === 1 ? null : [olderGroup];
  });
  await page.goto("/#/issues");
  const search = page.getByRole("combobox", { name: "통합 검색" });
  await search.fill("해저");
  await expect(page.getByRole("listbox")).toContainText("검색하지 못했습니다");
  await page.getByRole("button", { name: "검색 다시 시도" }).click();
  await expect(
    page.getByRole("option", { name: /오래된 해저 케이블 기록/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "통합 검색 지우기" }).click();
  await expect(search).toHaveValue("");
  await expect(page.getByRole("listbox")).toBeHidden();
  await search.fill("없는 이슈");
  await expect(page.getByRole("listbox")).toContainText("결과가 없습니다");
  await search.fill("NVDA");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(1);
  await search.press("Enter");
  await expect(page).toHaveURL(/#\/stocks\/NVDA$/);
});
