import { afterEach, expect, test, vi } from "vitest";
import { ApiError, createAlert, getMe, searchListings } from "./api";

function stubFetch(status: number, body: unknown) {
  const mock = vi.fn().mockResolvedValue({
    ok: status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => vi.unstubAllGlobals());

test("getMe returns user", async () => {
  stubFetch(200, { id: 1, email: "a@b.com", telegram_linked: false, is_admin: false });
  const me = await getMe();
  expect(me?.email).toBe("a@b.com");
});

test("getMe returns null on 401", async () => {
  stubFetch(401, { detail: "not authenticated" });
  expect(await getMe()).toBeNull();
});

test("searchListings builds query string and skips empty params", async () => {
  const mock = stubFetch(200, { listings: [], newly_tracked: true });
  await searchListings({ city: "חיפה", max_price: 6000, neighborhood: "", sort: "newest" });
  const url = mock.mock.calls[0][0] as string;
  expect(url).toContain("/api/listings?");
  expect(url).toContain(`city=${encodeURIComponent("חיפה")}`);
  expect(url).toContain("max_price=6000");
  expect(url).not.toContain("neighborhood");
  expect(url).not.toContain("min_price");
});

test("createAlert posts json body", async () => {
  const mock = stubFetch(201, { id: 1 });
  await createAlert({ name: "x", filters: { locations: [{ city: "חיפה" }] }, channels: ["telegram"] });
  const [url, init] = mock.mock.calls[0];
  expect(url).toBe("/api/alerts");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body).name).toBe("x");
});

test("errors carry status and server detail", async () => {
  stubFetch(429, { detail: "rate limit exceeded" });
  await expect(searchListings({ city: "חיפה" })).rejects.toMatchObject({
    status: 429,
    message: "rate limit exceeded",
  });
  stubFetch(500, {});
  await expect(searchListings({ city: "חיפה" })).rejects.toBeInstanceOf(ApiError);
});
