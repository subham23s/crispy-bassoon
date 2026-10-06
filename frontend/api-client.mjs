export class ApiError extends Error {
  constructor(message, status, body = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

function errorMessage(body, status) {
  if (typeof body === 'string' && body.trim()) return body;
  if (body && typeof body.detail === 'string') return body.detail;
  if (body && body.detail && typeof body.detail.message === 'string') return body.detail.message;
  return `Request failed (${status})`;
}

async function readBody(response) {
  if (response.status === 204) return {};
  try {
    return await response.json();
  } catch {
    return {};
  }
}

/**
 * A small API client whose credentials deliberately live only in this closure.
 * Refresh is attempted once for an authenticated request after a 401 response.
 */
export function createApiClient({
  baseUrl,
  fetchImpl = globalThis.fetch,
  onSessionExpired = () => {},
} = {}) {
  if (typeof fetchImpl !== 'function') throw new Error('A fetch implementation is required');

  const root = String(baseUrl || '').replace(/\/$/, '');
  let session = { accessToken: null, refreshToken: null };
  let expiringNotified = false;

  function setSession(tokens = {}) {
    session = {
      accessToken: tokens.access_token || tokens.accessToken || null,
      refreshToken: tokens.refresh_token || tokens.refreshToken || null,
    };
    expiringNotified = false;
  }

  function clearSession() {
    session = { accessToken: null, refreshToken: null };
  }

  function getSession() {
    return { ...session };
  }

  function notifySessionExpired() {
    clearSession();
    if (expiringNotified) return;
    expiringNotified = true;
    onSessionExpired();
  }

  async function send(path, options = {}, authenticated = true, allowRefresh = true) {
    const { auth: _auth, ...requestOptions } = options;
    const headers = new Headers(requestOptions.headers || {});
    if (requestOptions.body && !headers.has('content-type')) headers.set('content-type', 'application/json');
    if (authenticated && session.accessToken) headers.set('authorization', `Bearer ${session.accessToken}`);

    const response = await fetchImpl(`${root}${path}`, { ...requestOptions, headers });
    const body = await readBody(response);
    if (response.ok) return body;

    if (response.status === 401 && authenticated && allowRefresh && session.refreshToken && path !== '/auth/refresh') {
      try {
        await refreshSession();
        return send(path, options, authenticated, false);
      } catch (refreshError) {
        notifySessionExpired();
        throw refreshError;
      }
    }

    if (response.status === 401 && authenticated) notifySessionExpired();
    throw new ApiError(errorMessage(body, response.status), response.status, body);
  }

  async function refreshSession() {
    if (!session.refreshToken) throw new ApiError('No refresh token is available.', 401);
    const response = await fetchImpl(`${root}/auth/refresh`, {
      method: 'POST',
      headers: new Headers({ 'content-type': 'application/json' }),
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    const body = await readBody(response);
    if (!response.ok) throw new ApiError(errorMessage(body, response.status), response.status, body);
    setSession(body);
    return body;
  }

  async function request(path, options = {}) {
    const authenticated = options.auth !== false;
    return send(path, options, authenticated, true);
  }

  return {
    request,
    getSession,
    setSession,
    clearSession,
    refresh: refreshSession,
    login(email, password) {
      return request('/auth/login', {
        method: 'POST',
        auth: false,
        body: JSON.stringify({ email, password }),
      }).then((result) => {
        setSession(result);
        return result;
      });
    },
    register(email, password) {
      return request('/auth/register', {
        method: 'POST',
        auth: false,
        body: JSON.stringify({ email, password }),
      }).then((result) => {
        setSession(result);
        return result;
      });
    },
    me() {
      return request('/auth/me');
    },
    logout() {
      const refreshToken = session.refreshToken;
      return request('/auth/logout', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).finally(clearSession);
    },
    health() {
      return request('/health', { auth: false });
    },
    healthDetailed() {
      return request('/health/detailed', { auth: false });
    },
  };
}
