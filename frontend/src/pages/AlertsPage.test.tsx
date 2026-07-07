import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import type { Me } from "../types";
import AlertsPage from "./AlertsPage";

const ME: Me = { id: 1, email: "a@b.com", telegram_linked: false, is_admin: false };

const ALERT = {
  id: 5, user_id: 1, name: "חיפה עד 6000", active: true, channels: ["email"],
  filters: { locations: [{ city: "חיפה" }], max_price: 6000 },
};

function stubApi(routes: Record<string, unknown>) {
  const mock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const body = routes[key] ?? {};
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => vi.unstubAllGlobals());

test("signed out shows login prompt", () => {
  render(<AlertsPage me={null} />);
  expect(screen.getByRole("link", { name: /התחברות/ })).toHaveAttribute("href", "/api/auth/login");
});

test("lists alerts and toggles one", async () => {
  const mock = stubApi({
    "GET /api/alerts": { alerts: [ALERT] },
    "POST /api/alerts/5/active": { ...ALERT, active: false },
  });
  render(<AlertsPage me={ME} />);
  expect(await screen.findByText("חיפה עד 6000")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "השהיה" }));
  await waitFor(() =>
    expect(mock.mock.calls.some(([url, init]) =>
      url === "/api/alerts/5/active" && (init as RequestInit)?.method === "POST")).toBe(true)
  );
});

test("creates an alert from the form", async () => {
  const mock = stubApi({
    "GET /api/alerts": { alerts: [] },
    "POST /api/alerts": { ...ALERT, id: 9 },
  });
  render(<AlertsPage me={ME} />);
  await userEvent.click(await screen.findByRole("button", { name: "התראה חדשה" }));
  await userEvent.type(screen.getByLabelText(/שם ההתראה/), "החיפוש שלי");
  await userEvent.type(screen.getByLabelText(/עיר/), "חיפה");
  await userEvent.click(screen.getByRole("button", { name: "שמירה" }));
  await waitFor(() => {
    const call = mock.mock.calls.find(([url, init]) =>
      url === "/api/alerts" && (init as RequestInit)?.method === "POST");
    expect(call).toBeTruthy();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body.name).toBe("החיפוש שלי");
    expect(body.filters.locations).toEqual([{ city: "חיפה" }]);
    expect(body.channels).toContain("email");
  });
});

test("mints telegram link", async () => {
  stubApi({
    "GET /api/alerts": { alerts: [] },
    "POST /api/telegram/link": { link: "https://t.me/bot?start=tok", expires_minutes: 15 },
  });
  render(<AlertsPage me={ME} />);
  await userEvent.click(await screen.findByRole("button", { name: "חיבור טלגרם" }));
  const link = await screen.findByRole("link", { name: /פתיחת הבוט/ });
  expect(link).toHaveAttribute("href", "https://t.me/bot?start=tok");
  expect(screen.getByText(/15 דקות/)).toBeInTheDocument();
});
