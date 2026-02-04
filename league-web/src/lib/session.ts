import type { UserSession } from "./types/user";

const SESSION_KEY = "league.session.user";

export function saveSessionUser(user: UserSession): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(user));
  console.debug("[session] saved user", { key: SESSION_KEY });
}

export function loadSessionUser(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) {
    console.debug("[session] missing user", { key: SESSION_KEY });
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as UserSession;
    console.debug("[session] loaded user", { key: SESSION_KEY });
    return parsed;
  } catch (error) {
    console.debug("[session] parse failed", { key: SESSION_KEY, error });
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function clearSessionUser(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_KEY);
  console.debug("[session] cleared user", { key: SESSION_KEY });
}
