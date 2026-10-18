const AUTH_KEY = "plasma_demo_auth";

function readAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const auth = JSON.parse(raw);
    return auth?.token && auth?.expires_at ? auth : null;
  } catch {
    return null;
  }
}

function expiryTime(value) {
  if (!value) return 0;
  if (typeof value === "number") return value < 10_000_000_000 ? value * 1000 : value;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function getAuth() {
  const auth = readAuth();
  if (!auth || expiryTime(auth.expires_at) <= Date.now()) {
    clearAuth();
    return null;
  }
  return auth;
}

export function getAuthToken() {
  return getAuth()?.token || "";
}

export function getUsername() {
  return getAuth()?.username || "";
}

export function setAuth(auth) {
  if (!auth?.token || !auth?.username || !auth?.expires_at) {
    throw new Error("Login response did not include a usable token");
  }
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
  window.dispatchEvent(new CustomEvent("plasma:auth-changed"));
}

export function clearAuth(notify = true) {
  if (localStorage.getItem(AUTH_KEY)) localStorage.removeItem(AUTH_KEY);
  if (notify) window.dispatchEvent(new CustomEvent("plasma:auth-expired"));
}

export function authorizationHeader() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function handleUnauthorized() {
  clearAuth();
}
