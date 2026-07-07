import { useState } from "react";
import { ApiError, searchListings } from "../api";
import { EMPTY_FILTERS, FilterForm, filtersToSearchParams, type FilterValues } from "../components/FilterForm";
import { ListingCard } from "../components/ListingCard";
import type { Listing } from "../types";

const PAGE_SIZE = 50;

export default function SearchPage() {
  const [values, setValues] = useState<FilterValues>(EMPTY_FILTERS);
  const [listings, setListings] = useState<Listing[] | null>(null);
  const [newlyTracked, setNewlyTracked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  async function run(nextOffset: number) {
    setError(null);
    try {
      const result = await searchListings({
        ...filtersToSearchParams(values),
        limit: PAGE_SIZE,
        offset: nextOffset,
      });
      setNewlyTracked(result.newly_tracked);
      setListings((previous) =>
        nextOffset === 0 ? result.listings : [...(previous ?? []), ...result.listings]
      );
      setOffset(nextOffset);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "שגיאה בחיפוש");
    }
  }

  const lastPageFull = listings !== null && listings.length - offset === PAGE_SIZE;

  return (
    <div>
      <h2>חיפוש דירות</h2>
      <FilterForm value={values} onChange={setValues} onSubmit={() => run(0)} submitLabel="חיפוש" />
      {error && <p className="error">{error}</p>}
      {newlyTracked && (
        <div className="banner">
          אנחנו אוספים מודעות לאזור הזה — כדאי לבדוק שוב בעוד רבע שעה.
        </div>
      )}
      {listings !== null && listings.length === 0 && !newlyTracked && <p>לא נמצאו דירות.</p>}
      {listings?.map((listing) => (
        <ListingCard listing={listing} key={listing.id} />
      ))}
      {lastPageFull && (
        <button className="secondary" onClick={() => run(offset + PAGE_SIZE)}>
          טען עוד
        </button>
      )}
    </div>
  );
}
