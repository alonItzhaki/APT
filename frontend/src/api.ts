import type { Alert, AlertFilters, Listing, Me, SourceState } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `שגיאה (${response.status})`
    );
  }
  return body as T;
}

export type SearchParams = { city: string; neighborhood?: string; sort?: "newest" | "price"; limit?: number; offset?: number } & Partial<Omit<AlertFilters, "locations">>;

export type AlertBody = { name: string; filters: AlertFilters; channels: string[] };

export async function getMe(): Promise<Me | null> {
  const response = await fetch("/api/me");
  if (response.status === 401) return null;
  if (!response.ok) throw new ApiError(response.status, "failed to load user");
  return (await response.json()) as Me;
}

export function logout(): Promise<void> {
  return request("/api/auth/logout", { method: "POST" });
}

export function searchListings(params: SearchParams): Promise<{ listings: Listing[]; newly_tracked: boolean }> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) {
      query.set(key, String(value));
    }
  }
  return request(`/api/listings?${query.toString()}`);
}

export async function listAlerts(): Promise<Alert[]> {
  const payload = await request<{ alerts: Alert[] }>("/api/alerts");
  return payload.alerts;
}

export function createAlert(body: AlertBody): Promise<Alert> {
  return request("/api/alerts", { method: "POST", body: JSON.stringify(body) });
}

export function updateAlert(id: number, body: AlertBody): Promise<Alert> {
  return request(`/api/alerts/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function setAlertActive(id: number, active: boolean): Promise<Alert> {
  return request(`/api/alerts/${id}/active`, { method: "POST", body: JSON.stringify({ active }) });
}

export function deleteAlert(id: number): Promise<void> {
  return request(`/api/alerts/${id}`, { method: "DELETE" });
}

export function mintTelegramLink(): Promise<{ link: string; expires_minutes: number }> {
  return request("/api/telegram/link", { method: "POST" });
}

export function deleteAccount(): Promise<void> {
  return request("/api/me", { method: "DELETE" });
}

export function adminHealth(): Promise<{ sources: SourceState[]; counts: Record<string, number> }> {
  return request("/api/admin/health");
}

export function setSourceEnabled(source: string, enabled: boolean): Promise<SourceState> {
  return request(`/api/admin/sources/${source}`, { method: "POST", body: JSON.stringify({ enabled }) });
}
