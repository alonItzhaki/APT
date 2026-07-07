import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import type { Me } from "../types";
import AdminPage from "./AdminPage";

const ADMIN: Me = { id: 1, email: "admin@b.com", telegram_linked: false, is_admin: true };

afterEach(() => vi.unstubAllGlobals());

test("non-admin sees no access", () => {
  render(<AdminPage me={null} />);
  expect(screen.getByText("אין הרשאה")).toBeInTheDocument();
});

test("admin sees counts, sources, and can toggle", async () => {
  const health = {
    sources: [{ source: "yad2", enabled: true, last_run: null, last_success: "2026-07-07T12:00:00+00:00", last_error: null }],
    counts: { users: 3, alerts: 5, listings: 42 },
  };
  const mock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === "/api/admin/health") {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(health) });
    }
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ source: "yad2", enabled: false, last_run: null, last_success: null, last_error: null }),
    });
  });
  vi.stubGlobal("fetch", mock);
  render(<AdminPage me={ADMIN} />);
  expect(await screen.findByText(/42/)).toBeInTheDocument();
  expect(screen.getByText("yad2")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "השבתה" }));
  expect(
    mock.mock.calls.some(([url, init]) =>
      url === "/api/admin/sources/yad2" && (init as RequestInit)?.method === "POST")
  ).toBe(true);
});
