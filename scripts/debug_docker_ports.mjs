import net from 'node:net';
import { execSync } from 'node:child_process';

const ENDPOINT = 'http://127.0.0.1:7379/ingest/8904c5b2-27d3-4134-bc13-984121caf5c6';
const SESSION_ID = 'b241d7';
const pendingLogs = [];
const RUN_ID = process.env.DEBUG_RUN_ID || 'pre-run';

function safeExec(cmd) {
  try {
    return execSync(cmd, { encoding: 'utf8' }).trim();
  } catch (e) {
    return String(e?.message || e);
  }
}

function log({ hypothesisId, location, message, data, runId = RUN_ID }) {
  // #region agent log
  const p = fetch(ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Debug-Session-Id': SESSION_ID,
    },
    keepalive: true,
    body: JSON.stringify({
      sessionId: SESSION_ID,
      runId,
      hypothesisId,
      location,
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  pendingLogs.push(p);
  // #endregion
}

function canBind(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', (err) => resolve({ ok: false, code: err?.code, message: String(err?.message || err) }));
    server.listen({ port, host: '0.0.0.0', exclusive: true }, () => {
      server.close(() => resolve({ ok: true }));
    });
  });
}

const portsToTest = [5432, 5433, 5434, 15433];

log({
  hypothesisId: 'A',
  location: 'scripts/debug_docker_ports.mjs:1',
  message: 'Starting docker/port debug',
  data: { portsToTest, runId: RUN_ID },
});

const bindResults = {};
for (const p of portsToTest) {
  // eslint-disable-next-line no-await-in-loop
  bindResults[String(p)] = await canBind(p);
}

log({
  hypothesisId: 'A',
  location: 'scripts/debug_docker_ports.mjs:59',
  message: 'Port bind test results',
  data: { bindResults },
});

log({
  hypothesisId: 'B',
  location: 'scripts/debug_docker_ports.mjs:68',
  message: 'Docker/compose environment snapshot',
  data: {
    dockerVersion: safeExec('docker version --format "{{json .}}"'),
    composeVersion: safeExec('docker compose version'),
    composeConfig: safeExec('docker compose config'),
    dockerPsA: safeExec('docker ps -a --format "table {{.Names}}\\t{{.Image}}\\t{{.Ports}}\\t{{.Status}}"'),
    composePs: safeExec('docker compose ps'),
  },
});

await Promise.allSettled(pendingLogs);

