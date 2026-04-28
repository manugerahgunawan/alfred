/**
 * Alfred API layer — communicates with the Alfred ADK agent on Cloud Run.
 *
 * INTEGRATION REQUIREMENTS:
 *  1. CORS: The Cloud Run backend must allow requests from this origin.
 *     Add CORS middleware to the ADK server, or configure via Cloud Run / load-balancer headers.
 *  2. VITE_GOOGLE_OAUTH_CLIENT_ID: Add your OAuth client ID to .env so the auth flow works.
 *     e.g.  VITE_GOOGLE_OAUTH_CLIENT_ID=123456789.apps.googleusercontent.com
 *     The redirect URI (window.location.origin) must be registered in GCP Console.
 */

const RAW_ALFRED_BASE_URL =
  (import.meta as unknown as { env: Record<string, string> }).env
    .VITE_ALFRED_BASE_URL || 'https://alfred-agent-gloaqqynxq-et.a.run.app';

function normalizeHttpsUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return trimmed;

  try {
    const url = new URL(trimmed);
    if (url.protocol === 'http:') {
      url.protocol = 'https:';
    }
    return url.toString().replace(/\/$/, '');
  } catch {
    return trimmed.replace(/^http:\/\//i, 'https://').replace(/\/$/, '');
  }
}

export const ALFRED_BASE_URL = normalizeHttpsUrl(RAW_ALFRED_BASE_URL);

const APP_NAME = 'alfred_agent';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ADKRunEventPart {
  text?: string;
  thoughtSignature?: string;
}

interface ADKRunEvent {
  content?: {
    role?: string;
    parts?: ADKRunEventPart[];
  };
  is_final_response?: boolean;
  author?: string;
}

// ─── Session ──────────────────────────────────────────────────────────────────

/**
 * Creates a new ADK session for the given user and stores the Google access
 * token in session state so Alfred's MCP tools can authenticate.
 *
 * @returns the session ID string
 */
export async function createAlfredSession(
  userId: string,
  accessToken: string,
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Bangkok'
): Promise<string> {
  const res = await fetch(
    `${ALFRED_BASE_URL}/apps/${APP_NAME}/users/${encodeURIComponent(userId).replace('%40', '@')}/sessions`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        state: {
          ALFRED_ACCESS_TOKEN: accessToken,
          ALFRED_TIMEZONE: timezone,
        },
      }),
    }
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Session creation failed (${res.status}): ${body}`);
  }

  const data = (await res.json()) as { id?: string; session_id?: string };
  const id = data.id ?? data.session_id;
  if (!id) throw new Error('Session created but no ID returned');
  return id;
}

// ─── Run ──────────────────────────────────────────────────────────────────────

export interface AlfredResponse {
  text: string;
  thought?: string;
}

/**
 * Sends a natural-language message to Alfred and returns the reply + thought.
 */
export async function sendToAlfred(
  userId: string,
  sessionId: string,
  accessToken: string,
  message: string
): Promise<AlfredResponse> {
  const res = await fetch(
    `${ALFRED_BASE_URL}/run`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        app_name: APP_NAME,
        user_id: userId,
        session_id: sessionId,
        new_message: {
          role: 'user',
          parts: [{ text: message }],
        },
      }),
    }
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Alfred run failed (${res.status}): ${body}`);
  }

  const contentType = res.headers.get('content-type') ?? '';
  console.log('[alfred] content-type:', contentType);
  if (contentType.includes('text/event-stream')) {
    const text = await res.text();
    return parseSSEFinalTextWithThought(text);
  }

  const data = (await res.json()) as ADKRunEvent[];
  console.log('[alfred] json events:', data);
  return extractFinalTextWithThought(Array.isArray(data) ? data : []);
}

// ─── Response parsing ─────────────────────────────────────────────────────────

function parseSSEFinalTextWithThought(sseText: string): AlfredResponse {
  const lines = sseText.split('\n');
  let lastText = '';
  let thought = '';
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    try {
      const ev = JSON.parse(line.slice(6)) as ADKRunEvent;
      console.log('[alfred:sse]', ev);
      if (ev.is_final_response && ev.content?.parts) {
        for (const part of ev.content.parts) {
          if (part.thoughtSignature) thought = part.thoughtSignature;
          if (part.text) lastText = part.text;
        }
      }
    } catch {
      // skip malformed SSE line
    }
  }
  return { text: lastText || FALLBACK_REPLY, thought: thought || undefined };
}

function extractFinalTextWithThought(events: ADKRunEvent[]): AlfredResponse {
  let lastText = '';
  let thought = '';
  // Prefer explicit final-response flag
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.is_final_response && ev.content?.parts) {
      for (const part of ev.content.parts) {
        if (part.thoughtSignature) thought = part.thoughtSignature;
        if (part.text) lastText = part.text;
      }
    }
  }
  // Fallback: last model text
  if (!lastText) {
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev.content?.role === 'model' && ev.content.parts) {
        for (const part of ev.content.parts) {
          if (part.thoughtSignature) thought = part.thoughtSignature;
          if (part.text) lastText = part.text;
        }
      }
    }
  }
  return { text: lastText || FALLBACK_REPLY, thought: thought || undefined };
}

const FALLBACK_REPLY = 'I am unable to respond at this moment, sir.';

// ─── Google OAuth helpers ─────────────────────────────────────────────────────

const GOOGLE_SCOPES = [
  'openid',
  'email',
  'profile',
  'https://www.googleapis.com/auth/calendar',
  'https://www.googleapis.com/auth/gmail.modify',
  'https://www.googleapis.com/auth/contacts',
].join(' ');

/**
 * Redirects to Google OAuth implicit flow. On return, `parseOAuthFragment()`
 * should be called to extract the access token from the URL hash.
 *
 * Requires VITE_GOOGLE_OAUTH_CLIENT_ID to be set in .env
 */
export function startGoogleOAuth(): void {
  const clientId = (import.meta as unknown as { env: Record<string, string> }).env
    .VITE_GOOGLE_OAUTH_CLIENT_ID;
  if (!clientId) {
    throw new Error(
      'VITE_GOOGLE_OAUTH_CLIENT_ID is not set. Add it to your .env file to enable Google sign-in.'
    );
  }
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: window.location.origin,
    response_type: 'token',
    scope: GOOGLE_SCOPES,
    prompt: 'select_account',
  });
  window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
}

/**
 * Parses the URL hash fragment for an OAuth access_token returned by Google.
 * Call this once on mount. Returns null if not an OAuth callback.
 */
export function parseOAuthFragment(): string | null {
  const hash = window.location.hash;
  if (!hash.includes('access_token')) return null;
  const params = new URLSearchParams(hash.slice(1)); // strip leading '#'
  return params.get('access_token');
}

/**
 * Fetches the authenticated user's email address from Google.
 */
export async function fetchUserEmail(accessToken: string): Promise<string> {
  const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(`Failed to fetch user info: ${res.status}`);
  const data = (await res.json()) as { email?: string };
  return data.email ?? 'user@example.com';
}
