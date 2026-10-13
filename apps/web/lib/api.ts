export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

let refresh: Promise<Response> | null = null;
export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`/api${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" }); }
  catch { throw new ApiError("서버에 연결할 수 없습니다. 연결 상태를 확인하세요.", 0); }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    refresh ||= fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" }).finally(() => { refresh = null; });
    if ((await refresh).ok) return api<T>(path, options, false);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "요청이 실패했습니다." }));
    const message = typeof payload.detail === "string" ? payload.detail : "입력 값을 확인하세요.";
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const jsonBody = (data: unknown) => JSON.stringify(data);
export function pace(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}′${String(total % 60).padStart(2, "0")}″`;
}
