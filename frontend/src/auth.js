// HTTP Basic credentials for the API gate.
//
// The dashboard is served as a static shell, so the browser no longer shows its
// own sign-in prompt. The API still requires credentials, so the app keeps them
// here and attaches them to every request; a 401 clears them and asks again.

const STORAGE_KEY = "mailmatrix.basic-auth";

export function getBasicAuth() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && parsed.user ? parsed : null;
  } catch {
    return null;
  }
}

export function setBasicAuth(user, password) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, password }));
}

export function clearBasicAuth() {
  localStorage.removeItem(STORAGE_KEY);
}

export function basicAuthHeader() {
  const creds = getBasicAuth();
  if (!creds) return null;
  return `Basic ${btoa(`${creds.user}:${creds.password}`)}`;
}

export function requestCredentials() {
  clearBasicAuth();
  window.dispatchEvent(new CustomEvent("mailmatrix:auth-required"));
}