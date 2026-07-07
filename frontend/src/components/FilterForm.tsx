import type { AlertFilters } from "../types";
import type { SearchParams } from "../api";

export interface FilterValues {
  city: string; neighborhood: string;
  min_price: string; max_price: string;
  min_rooms: string; max_rooms: string;
  min_size_sqm: string;
  require_mamad: boolean; require_elevator: boolean;
}

export const EMPTY_FILTERS: FilterValues = {
  city: "", neighborhood: "", min_price: "", max_price: "",
  min_rooms: "", max_rooms: "", min_size_sqm: "",
  require_mamad: false, require_elevator: false,
};

function toNumber(value: string): number | undefined {
  return value.trim() === "" ? undefined : Number(value);
}

export function filtersToSearchParams(values: FilterValues): SearchParams {
  const params: SearchParams = { city: values.city.trim() };
  if (values.neighborhood.trim()) params.neighborhood = values.neighborhood.trim();
  for (const key of ["min_price", "max_price", "min_rooms", "max_rooms", "min_size_sqm"] as const) {
    const parsed = toNumber(values[key]);
    if (parsed !== undefined) (params as Record<string, unknown>)[key] = parsed;
  }
  if (values.require_mamad) params.require_mamad = true;
  if (values.require_elevator) params.require_elevator = true;
  return params;
}

export function filtersToAlertFilters(values: FilterValues): AlertFilters {
  const { city, neighborhood, ...rest } = filtersToSearchParams(values);
  return { locations: [{ city, ...(neighborhood ? { neighborhood } : {}) }], ...rest };
}

export function alertFiltersToValues(filters: AlertFilters): FilterValues {
  const location = filters.locations[0] ?? { city: "" };
  return {
    city: location.city,
    neighborhood: location.neighborhood ?? "",
    min_price: filters.min_price?.toString() ?? "",
    max_price: filters.max_price?.toString() ?? "",
    min_rooms: filters.min_rooms?.toString() ?? "",
    max_rooms: filters.max_rooms?.toString() ?? "",
    min_size_sqm: filters.min_size_sqm?.toString() ?? "",
    require_mamad: filters.require_mamad ?? false,
    require_elevator: filters.require_elevator ?? false,
  };
}

interface Props {
  value: FilterValues;
  onChange: (value: FilterValues) => void;
  onSubmit: () => void;
  submitLabel: string;
}

export function FilterForm({ value, onChange, onSubmit, submitLabel }: Props) {
  const set = (patch: Partial<FilterValues>) => onChange({ ...value, ...patch });
  const number = (id: keyof FilterValues, label: string) => (
    <div>
      <label htmlFor={id}>{label}</label>
      <input id={id} type="number" value={value[id] as string}
             onChange={(event) => set({ [id]: event.target.value } as Partial<FilterValues>)} />
    </div>
  );
  return (
    <form
      className="filters"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="full">
        <label htmlFor="city">עיר *</label>
        <input id="city" type="text" value={value.city}
               onChange={(event) => set({ city: event.target.value })} />
      </div>
      <div className="full">
        <label htmlFor="neighborhood">שכונה</label>
        <input id="neighborhood" type="text" value={value.neighborhood}
               onChange={(event) => set({ neighborhood: event.target.value })} />
      </div>
      {number("min_price", "מחיר מ-")}
      {number("max_price", "מחיר עד")}
      {number("min_rooms", "חדרים מ-")}
      {number("max_rooms", "חדרים עד")}
      {number("min_size_sqm", 'גודל מינימלי במ"ר')}
      <label htmlFor="require_mamad" className="checkbox">
        <input id="require_mamad" type="checkbox" checked={value.require_mamad}
               onChange={(event) => set({ require_mamad: event.target.checked })} />
        ממ"ד
      </label>
      <label htmlFor="require_elevator" className="checkbox">
        <input id="require_elevator" type="checkbox" checked={value.require_elevator}
               onChange={(event) => set({ require_elevator: event.target.checked })} />
        מעלית
      </label>
      <div className="full">
        <button type="submit" disabled={!value.city.trim()}>{submitLabel}</button>
      </div>
    </form>
  );
}
