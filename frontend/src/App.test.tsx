import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

function stubMe(me: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/me") {
        return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(me) });
      }
      if (url === "/api/auth/logout") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
      }
      if (url === "/api/alerts") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ alerts: [] }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    })
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

test("signed out shows google login link", async () => {
  stubMe({ detail: "no" }, 401);
  render(<App />);
  const link = await screen.findByRole("link", { name: /Google/ });
  expect(link).toHaveAttribute("href", "/api/auth/login");
});

test("signed in shows email, logout works", async () => {
  stubMe({ id: 1, email: "a@b.com", telegram_linked: false, is_admin: false });
  render(<App />);
  expect(await screen.findByText("a@b.com")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /ניהול/ })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "יציאה" }));
  await waitFor(() => expect(screen.getByRole("link", { name: /Google/ })).toBeInTheDocument());
});

test("admin sees admin nav and hash routing switches pages", async () => {
  stubMe({ id: 1, email: "admin@b.com", telegram_linked: false, is_admin: true });
  render(<App />);
  expect(await screen.findByRole("link", { name: "ניהול" })).toBeInTheDocument();
  window.location.hash = "#/alerts";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByRole("heading", { name: "ההתראות שלי" })).toBeInTheDocument();
});
