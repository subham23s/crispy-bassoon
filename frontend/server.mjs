import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const port = Number(process.env.PORT || 3000);

// Keep the static server intentionally allow-listed. Source, config, hidden, and
// arbitrary files in the project directory must never become web assets.
export const PUBLIC_ASSETS = new Set(['index.html', 'app.js', 'api-client.mjs', 'styles.css']);
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

function requestedAsset(requestUrl) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(requestUrl || '/', 'http://localhost').pathname);
  } catch {
    return null;
  }
  if (pathname === '/') return 'index.html';
  if (!pathname.startsWith('/')) return null;
  const asset = pathname.slice(1);
  if (!asset || asset.includes('/') || asset.startsWith('.') || asset.includes('\\')) return null;
  return PUBLIC_ASSETS.has(asset) ? asset : null;
}

export function createStaticServer({ publicRoot = root } = {}) {
  return createServer(async (request, response) => {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405, { Allow: 'GET, HEAD' });
      response.end('Method not allowed');
      return;
    }

    const asset = requestedAsset(request.url);
    if (!asset) {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Not found');
      return;
    }

    const file = resolve(publicRoot, asset);
    try {
      const body = await readFile(file);
      response.writeHead(200, {
        'Content-Type': mime[extname(file)] || 'application/octet-stream',
        'Cache-Control': 'no-cache',
        'X-Content-Type-Options': 'nosniff',
      });
      response.end(request.method === 'HEAD' ? undefined : body);
    } catch {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Not found');
    }
  });
}

export function startServer(listenPort = port) {
  const server = createStaticServer();
  return server.listen(listenPort, () => console.log(`CyberSecRA-X web dashboard: http://localhost:${listenPort}`));
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : '';
if (invokedPath === fileURLToPath(import.meta.url)) startServer();
