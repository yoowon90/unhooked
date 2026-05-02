import * as SecureStore from 'expo-secure-store';

// For dev: use your Mac's local IP so a physical device can reach it.
// Find it with: ifconfig | grep "inet " (look for 192.168.x.x)
// Example: 'http://192.168.1.42:5001/api/v1'
const BASE_URL = __DEV__
  ? 'http://localhost:5001/api/v1'
  : 'https://your-production-url.com/api/v1';

const TOKEN_KEY = 'auth_token';

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}
export async function saveToken(token: string): Promise<void> {
  return SecureStore.setItemAsync(TOKEN_KEY, token);
}
export async function deleteToken(): Promise<void> {
  return SecureStore.deleteItemAsync(TOKEN_KEY);
}

async function request<T>(method: string, path: string, body?: object): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data as T;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  first_name: string;
  zipcode: string;
  last_purchase_date: string | null;
}

export interface WishItem {
  id: number;
  name: string;
  brand: string;
  category: string;
  tag: string | null;
  description: string;
  link: string;
  image_url: string | null;
  price: number;
  taxed_price: number;
  delivery_fee: number;
  total_price: number;
  favorited: boolean;
  unhooked: boolean;
  purchased: boolean;
  ineligible: boolean;
  date: string;
  purchase_date: string | null;
  unhooked_date: string | null;
  wish_period_seconds: number | null;
}

export type ItemStatus = 'wishlist' | 'purchased' | 'unhooked';

export interface CreateItemPayload {
  name: string;
  brand: string;
  category: string;
  link: string;
  price: number;
  delivery_fee?: number;
  tag?: string;
  description?: string;
  image_url?: string;
}

export interface ExtractedItem {
  success: boolean;
  name: string | null;
  price: string | null;
  brand: string | null;
  description: string | null;
  currency: string | null;
  image_url: string | null;
}

export interface ReportSummary {
  last_purchase_date: string | null;
  spenditure: Record<string, number>;
  saves: Record<string, number>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>('POST', '/auth/login', { email, password }),

  signup: (email: string, first_name: string, password: string, zipcode: string) =>
    request<{ token: string; user: User }>('POST', '/auth/signup', { email, first_name, password, zipcode }),

  me: () => request<User>('GET', '/auth/me'),
};

// ── WishItems ─────────────────────────────────────────────────────────────────

export const wishItemsApi = {
  list: (params?: { status?: ItemStatus; category?: string; brand?: string }) => {
    const qs = params ? new URLSearchParams(params as Record<string, string>).toString() : '';
    return request<WishItem[]>('GET', `/wishitems${qs ? `?${qs}` : ''}`);
  },

  create: (payload: CreateItemPayload) =>
    request<WishItem>('POST', '/wishitems', payload),

  get: (id: number) =>
    request<WishItem>('GET', `/wishitems/${id}`),

  update: (id: number, fields: Partial<CreateItemPayload>) =>
    request<WishItem>('PATCH', `/wishitems/${id}`, fields),

  delete: (id: number) =>
    request<{}>('DELETE', `/wishitems/${id}`),

  setStatus: (id: number, status: ItemStatus) =>
    request<WishItem>('POST', `/wishitems/${id}/status`, { status }),

  toggleFavorite: (id: number) =>
    request<WishItem>('POST', `/wishitems/${id}/favorite`),

  removeImage: (id: number) =>
    request<{}>('DELETE', `/wishitems/${id}/image`),
};

// ── URL Extraction ────────────────────────────────────────────────────────────

export const extractApi = {
  fromUrl: (url: string) =>
    request<ExtractedItem>('POST', '/extract', { url }),
};

// ── Reports ───────────────────────────────────────────────────────────────────

export const reportsApi = {
  summary: () =>
    request<ReportSummary>('GET', '/reports/summary'),

  generate: (start_date: string, end_date: string) =>
    request<any>('POST', '/reports/generate', { start_date, end_date }),
};
