import type { ListResponse, Paginated } from "@/lib/api/types";

const API_BASE = "/api";

export type ListParams = Record<string, string | number | boolean | null | undefined>;

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function toQuery(params: ListParams = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const value = query.toString();
  return value ? `?${value}` : "";
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      ...init.headers,
    },
  });

  if (response.status === 401 || response.status === 403) {
    window.location.assign(`/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`);
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function listResource<T>(path: string, params?: ListParams) {
  const data = await apiFetch<ListResponse<T>>(`${path}${toQuery(params)}`);
  return Array.isArray(data) ? data : data.results;
}

export async function paginatedResource<T>(path: string, params: ListParams = {}) {
  return apiFetch<Paginated<T>>(`${path}${toQuery({ page_size: 100, ...params })}`);
}

export async function getResource<T>(path: string) {
  return apiFetch<T>(path);
}
