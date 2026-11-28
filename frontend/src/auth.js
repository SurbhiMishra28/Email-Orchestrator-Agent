// Credentials for the API gate.
//
// The dashboard is a static shell, so the browser never shows its own sign-in
// prompt. The app keeps a session here and attaches it to every request:
//
//   { token }              -> Authorization: Bearer <jwt>   (sign-in, demo)
//   { user, password }     -> Authorization: Basic <...>    (configured gate)
//
// A 401 clears the session and asks again. "Keep me signed in" stores it in
// localStorage; otherwise it lives in sessionStorage and dies with the tab.

const SESSION_KEY = "mailmatrix.session";
const LAST_USER_KEY = "mailmatrix.last-user";

// RFC 7617 Basic credentials are UTF-8. ``btoa`` only accepts Latin-1, so a
// username or password with any other character would throw and surface as a
// generic sign-in failure.
export function encodeBasic(user, password) {
  const bytes = new TextEncoder().encode(`${user}:${password}`);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function readStore(store) {
  try {
    const raw = store.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed) return null;
    if (parsed.token) return { token: parsed.token };
    if (parsed.user) return { user: parsed.user, password: parsed.password };
    return null;
  } catch {
    return null;
  }
}

export function getSession() {
  return readStore(localStorage) || readStore(sessionStorage);
}

export function setSession(session, remember = true) {
  const payload = JSON.stringify(session);
  try {
    if (remember) {
      localStorage.setItem(SESSION_KEY, payload);
      sessionStorage.removeItem(SESSION_KEY);
    } else {
      sessionStorage.setItem(SESSION_KEY, payload);
      localStorage.removeItem(SESSION_KEY);
    }
    if (session.user) localStorage.setItem(LAST_USER_KEY, session.user);
  } catch {
    /* private mode or blocked storage: the in-memory header still works */
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* nothing stored */
  }
}

export function getLastUser() {
  try {
    return localStorage.getItem(LAST_USER_KEY) || "";
  } catch {
    return "";
  }
}

export function authHeader() {
  const session = getSession();
  if (!session) return null;
  if (session.token) return `Bearer ${session.token}`;
  return `Basic ${encodeBasic(session.user, session.password)}`;
}

// Kept for callers that only ever hold Basic credentials.
export function basicAuthHeader() {
  const session = getSession();
  if (!session || session.token) return null;
  return `Basic ${encodeBasic(session.user, session.password)}`;
}

export function requestCredentials() {
  clearSession();
  window.dispatchEvent(new CustomEvent("mailmatrix:auth-required"));
}