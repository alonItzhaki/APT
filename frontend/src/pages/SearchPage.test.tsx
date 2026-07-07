import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import SearchPage from "./SearchPage";

afterEach(() => vi.unstubAllGlobals());

function stubSearch(payload: unknown) {
  const mock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(payload) });
  vi.stubGlobal("fetch", mock);
  return mock;
}

test("searches and shows newly-tracked banner", async () => {
  const mock = stubSearch({ listings: [], newly_tracked: true });
  render(<SearchPage />);
  await userEvent.type(screen.getByLabelText(/עיר/), "אילת");
  await userEvent.click(screen.getByRole("button", { name: "חיפוש" }));
  expect(await screen.findByText(/אוספים מודעות/)).toBeInTheDocument();
  expect((mock.mock.calls[0][0] as string)).toContain("/api/listings?");
});

test("renders result cards", async () => {
  stubSearch({
    listings: [{
      id: "yad2:a1", source: "yad2", source_id: "a1", url: "https://e.com/a1",
      city: "חיפה", neighborhood: null, street: null, price: 5000, rooms: null,
      size_sqm: null, floor: null, has_mamad: null, has_elevator: null,
      tags: [], description: "", photo_urls: [],
    }],
    newly_tracked: false,
  });
  render(<SearchPage />);
  await userEvent.type(screen.getByLabelText(/עיר/), "חיפה");
  await userEvent.click(screen.getByRole("button", { name: "חיפוש" }));
  expect(await screen.findByText("₪5,000")).toBeInTheDocument();
});
