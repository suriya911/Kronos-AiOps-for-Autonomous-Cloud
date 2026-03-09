// ─── Kronos AIOps — PKCE OAuth2 Auth helper ───────────────────────────────────
//
// Implements the OAuth2 Authorization Code + PKCE flow against AWS Cognito
// Hosted UI. No library dependency — uses native crypto.subtle + URL APIs.
//
// Flow:
//   login()          → generate verifier/challenge → redirect to Cognito /authorize
//   handleCallback() → exchange ?code= for tokens → store in sessionStorage
//   getAccessToken() → return stored JWT (or null if expired/absent)
//   isAuthenticated()→ boolean
//   logout()         → clear tokens → redirect to Cognito /logout
// ─────────────────────────────────────────────────────────────────────────────

const COGNITO_DOMAIN  = (import.meta.env.VITE_COGNITO_DOMAIN   ?? '').replace(/\/$/, '');
const CLIENT_ID       =  import.meta.env.VITE_COGNITO_CLIENT_ID ?? '';
const REDIRECT_URI    = `${window.location.origin}/`;

const KEYS = {
  verifier:     'pkce_verifier',
  state:        'pkce_state',
  accessToken:  'access_token',
  idToken:      'id_token',
  refreshToken: 'refresh_token',
  expiresAt:    'token_expires_at',
} as const;

// ─── PKCE helpers ─────────────────────────────────────────────────────────────

function randomBase64Url(byteCount: number): string {
  const buf = crypto.getRandomValues(new Uint8Array(byteCount));
  return btoa(String.fromCharCode(...buf))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function sha256Base64Url(plain: string): Promise<string> {
  const data    = new TextEncoder().encode(plain);
  const hashBuf = await crypto.subtle.digest('SHA-256', data);
  const hashArr = Array.from(new Uint8Array(hashBuf));
  return btoa(String.fromCharCode(...hashArr))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

// ─── Public API ───────────────────────────────────────────────────────────────

/** Redirect to Cognito Hosted UI login page. */
export async function login(): Promise<void> {
  const verifier  = randomBase64Url(64);
  const state     = randomBase64Url(32);
  const challenge = await sha256Base64Url(verifier);

  sessionStorage.setItem(KEYS.verifier, verifier);
  sessionStorage.setItem(KEYS.state,    state);

  const url = new URL(`${COGNITO_DOMAIN}/oauth2/authorize`);
  url.searchParams.set('response_type',          'code');
  url.searchParams.set('client_id',              CLIENT_ID);
  url.searchParams.set('redirect_uri',           REDIRECT_URI);
  url.searchParams.set('scope',                  'openid email profile');
  url.searchParams.set('state',                  state);
  url.searchParams.set('code_challenge',         challenge);
  url.searchParams.set('code_challenge_method',  'S256');

  window.location.href = url.toString();
}

/**
 * Called on the OAuth callback (?code=…&state=…).
 * Exchanges the authorization code for tokens and stores them in sessionStorage.
 */
export async function handleCallback(): Promise<void> {
  const params   = new URLSearchParams(window.location.search);
  const code     = params.get('code');
  const state    = params.get('state');
  const verifier = sessionStorage.getItem(KEYS.verifier);
  const savedState = sessionStorage.getItem(KEYS.state);

  if (!code || !verifier) {
    throw new Error('Missing code or PKCE verifier');
  }
  if (state !== savedState) {
    throw new Error('OAuth state mismatch — possible CSRF');
  }

  const body = new URLSearchParams({
    grant_type:    'authorization_code',
    client_id:     CLIENT_ID,
    code,
    redirect_uri:  REDIRECT_URI,
    code_verifier: verifier,
  });

  const res = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body:    body.toString(),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Token exchange failed (${res.status}): ${text}`);
  }

  const tokens = await res.json() as {
    access_token:  string;
    id_token:      string;
    refresh_token?: string;
    expires_in:    number;
  };

  const expiresAt = Date.now() + tokens.expires_in * 1_000;

  sessionStorage.setItem(KEYS.accessToken,  tokens.access_token);
  sessionStorage.setItem(KEYS.idToken,      tokens.id_token);
  sessionStorage.setItem(KEYS.expiresAt,    String(expiresAt));
  if (tokens.refresh_token) {
    sessionStorage.setItem(KEYS.refreshToken, tokens.refresh_token);
  }

  // Clean up PKCE state
  sessionStorage.removeItem(KEYS.verifier);
  sessionStorage.removeItem(KEYS.state);
}

/**
 * Returns the stored access token if not expired, otherwise null.
 * Caller should redirect to login() when this returns null.
 */
export function getAccessToken(): string | null {
  const token     = sessionStorage.getItem(KEYS.accessToken);
  const expiresAt = sessionStorage.getItem(KEYS.expiresAt);
  if (!token || !expiresAt) return null;
  // Treat as expired 60s early to avoid edge-case 401s
  if (Date.now() > Number(expiresAt) - 60_000) return null;
  return token;
}

/** Returns true if a non-expired access token is present. */
export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}

/** Clear all tokens and redirect to Cognito logout endpoint. */
export function logout(): void {
  sessionStorage.removeItem(KEYS.accessToken);
  sessionStorage.removeItem(KEYS.idToken);
  sessionStorage.removeItem(KEYS.refreshToken);
  sessionStorage.removeItem(KEYS.expiresAt);

  const url = new URL(`${COGNITO_DOMAIN}/logout`);
  url.searchParams.set('client_id',   CLIENT_ID);
  url.searchParams.set('logout_uri',  REDIRECT_URI);

  window.location.href = url.toString();
}
