import type { Listing } from "../types";

function formatPrice(price: number | null | undefined): string {
  return price != null ? `₪${price.toLocaleString("he-IL")}` : "מחיר לא צוין";
}

export function ListingCard({ listing }: { listing: Listing }) {
  const locationParts = [listing.street, listing.neighborhood, listing.city].filter(Boolean);
  const badges: string[] = [];
  if (listing.rooms != null) badges.push(`${listing.rooms} חדרים`);
  if (listing.size_sqm != null) badges.push(`${listing.size_sqm} מ"ר`);
  if (listing.floor != null) badges.push(`קומה ${listing.floor}`);
  if (listing.has_mamad === true) badges.push('ממ"ד');
  if (listing.has_elevator === true) badges.push("מעלית");
  const snippet =
    listing.description.length > 120 ? `${listing.description.slice(0, 120)}...` : listing.description;
  return (
    <div className="card">
      {listing.photo_urls[0] && (
        <img src={listing.photo_urls[0]} alt="" style={{ width: "100%", borderRadius: 8 }} />
      )}
      <div className="price">{formatPrice(listing.price)}</div>
      <h3>{locationParts.join(", ")}</h3>
      <div>
        {badges.map((badge) => (
          <span className="badge" key={badge}>{badge}</span>
        ))}
      </div>
      {snippet && <p className="muted">{snippet}</p>}
      <a href={listing.url} target="_blank" rel="noopener noreferrer">לצפייה במודעה</a>
    </div>
  );
}
