import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { EMPTY_FILTERS, FilterForm, filtersToAlertFilters, filtersToSearchParams } from "./FilterForm";

test("submit disabled until city filled, calls onSubmit", async () => {
  const onSubmit = vi.fn();
  function Wrapper() {
    const [value, setValue] = useState(EMPTY_FILTERS);
    return <FilterForm value={value} onChange={setValue} onSubmit={onSubmit} submitLabel="חיפוש" />;
  }
  render(<Wrapper />);
  const submit = screen.getByRole("button", { name: "חיפוש" });
  expect(submit).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/עיר/), "חיפה");
  expect(submit).toBeEnabled();
  await userEvent.click(submit);
  expect(onSubmit).toHaveBeenCalled();
  expect(screen.getByLabelText('ממ"ד')).not.toBeChecked();
  expect(screen.getByLabelText("מעלית")).not.toBeChecked();
});

test("filtersToSearchParams drops empties and parses numbers", () => {
  const params = filtersToSearchParams({ ...EMPTY_FILTERS, city: " חיפה ", max_price: "6000", require_mamad: true });
  expect(params).toEqual({ city: "חיפה", max_price: 6000, require_mamad: true });
});

test("filtersToAlertFilters builds locations", () => {
  const filters = filtersToAlertFilters({ ...EMPTY_FILTERS, city: "חיפה", neighborhood: "הדר", min_rooms: "3" });
  expect(filters.locations).toEqual([{ city: "חיפה", neighborhood: "הדר" }]);
  expect(filters.min_rooms).toBe(3);
  expect(filters.max_price).toBeUndefined();
});
