import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Listing } from "../types";
import { ListingCard } from "./ListingCard";

const LISTING: Listing = {
  id: "yad2:a1", source: "yad2", source_id: "a1", url: "https://yad2.co.il/item/a1",
  city: "חיפה", neighborhood: "הדר", street: "הרצל", price: 5000, rooms: 3.5,
  size_sqm: 80, floor: 2, has_mamad: true, has_elevator: null,
  tags: [], description: "דירה יפה מאוד", photo_urls: [],
};

test("renders price, location, badges and link", () => {
  render(<ListingCard listing={LISTING} />);
  expect(screen.getByText("₪5,000")).toBeInTheDocument();
  expect(screen.getByText(/הרצל/)).toBeInTheDocument();
  expect(screen.getByText("3.5 חדרים")).toBeInTheDocument();
  expect(screen.getByText('ממ"ד')).toBeInTheDocument();
  expect(screen.queryByText("מעלית")).not.toBeInTheDocument();
  const link = screen.getByRole("link", { name: "לצפייה במודעה" });
  expect(link).toHaveAttribute("href", LISTING.url);
  expect(link).toHaveAttribute("target", "_blank");
});

test("handles missing price and photo", () => {
  render(<ListingCard listing={{ ...LISTING, price: null, photo_urls: [] }} />);
  expect(screen.getByText("מחיר לא צוין")).toBeInTheDocument();
});
