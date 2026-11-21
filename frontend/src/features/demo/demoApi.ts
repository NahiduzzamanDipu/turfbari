import { api } from "@/lib/api";

const DEMO_API_BASE = "/public/demo";

export function demoApi<T>(path: string, init: RequestInit & { json?: unknown } = {}) {
  return api<T>(`${DEMO_API_BASE}${path}`, init);
}
