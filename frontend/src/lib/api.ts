/**
 * Thin fetch wrapper for the Django API.
 * - Same-origin requests with the session cookie.
 * - Sends the CSRF token on unsafe methods (fetching /api/auth/csrf/ first if needed).
 * - Normalises the backend error envelope into ApiError.
 */

const CSRF_COOKIE = "turfbari_csrftoken";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export interface ApiErrorBody {
  code: string;
  message: string;
  fields: Record<string, string[]> | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string[]> | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.fields = body.fields;
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  await fetch("/api/auth/csrf/", { credentials: "same-origin" });
  return readCookie(CSRF_COOKIE) ?? "";
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  if (!SAFE_METHODS.has(method)) {
    headers.set("X-CSRFToken", await ensureCsrfToken());
  }

  const response = await fetch(`/api${path}`, { ...init, method, headers, body, credentials: "same-origin" });

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const envelope = (data as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError(
      response.status,
      envelope ?? { code: "network_error", message: "Something went wrong. Please try again.", fields: null },
    );
  }
  return data as T;
}
