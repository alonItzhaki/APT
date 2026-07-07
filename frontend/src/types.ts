export interface Location { city: string; neighborhood?: string | null }
export interface AlertFilters {
  locations: Location[];
  min_price?: number | null; max_price?: number | null;
  min_rooms?: number | null; max_rooms?: number | null;
  min_size_sqm?: number | null; min_floor?: number | null; max_floor?: number | null;
  require_mamad?: boolean; require_elevator?: boolean;
}
export interface Listing {
  id: string; source: string; source_id: string; url: string;
  city: string; neighborhood?: string | null; street?: string | null;
  price?: number | null; rooms?: number | null; size_sqm?: number | null;
  floor?: number | null; has_mamad?: boolean | null; has_elevator?: boolean | null;
  tags: string[]; description: string; photo_urls: string[];
}
export interface Alert {
  id: number; user_id: number; name: string;
  filters: AlertFilters; channels: string[]; active: boolean;
}
export interface Me { id: number; email: string; telegram_linked: boolean; is_admin: boolean }
export interface SourceState {
  source: string; enabled: boolean;
  last_run?: string | null; last_success?: string | null; last_error?: string | null;
}
