import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const pagePath = new URL('./static/index.html', import.meta.url);
const port = Number(process.env.PHASE3_SMOKE_PORT ?? 41739);

const server = createServer(async (request, response) => {
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'text/plain' }).end('ready');
    return;
  }
  if (request.url === '/api/items/1') {
    response.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({ id: '1', name: 'Smoke item', status: 'ready' }));
    return;
  }
  if (request.url === '/' || request.url === '/index.html') {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(await readFile(fileURLToPath(pagePath)));
    return;
  }
  response.writeHead(404, { 'content-type': 'text/plain' }).end('not found');
});

server.listen(port, '127.0.0.1');
