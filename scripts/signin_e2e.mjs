// Drives a real Chrome through "Continue with Google" using the DevTools protocol, with no
// dependencies (Node 22 has fetch and WebSocket built in). Prints one JSON object of checks.
// Usage: node scripts/signin_e2e.mjs <app url> <chrome binary> <scratch profile dir>
import { spawn } from 'node:child_process';

const [appUrl, chromeBinary, profile] = process.argv.slice(2);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const chrome = spawn(
  chromeBinary,
  ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9334', `--user-data-dir=${profile}`, 'about:blank'],
  { stdio: 'ignore' },
);
const checks = {};
try {
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(250);
    try {
      target = (await (await fetch('http://127.0.0.1:9334/json')).json()).find((t) => t.type === 'page');
    } catch {
      // Chrome is still starting.
    }
  }
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve) => (socket.onopen = resolve));
  let id = 0;
  const waiting = new Map();
  socket.onmessage = (message) => {
    const data = JSON.parse(message.data);
    if (data.id && waiting.has(data.id)) {
      waiting.get(data.id)(data.result);
      waiting.delete(data.id);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      waiting.set(++id, resolve);
      socket.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) =>
    (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })).result?.value;
  const until = async (expression, tries = 80) => {
    for (let i = 0; i < tries; i++) {
      if (await evaluate(expression)) return true;
      await sleep(500);
    }
    return false;
  };

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Page.navigate', { url: appUrl });
  const button = `[...document.querySelectorAll('[role=button]')].find((e) => e.textContent.includes('Continue with Google'))`;
  checks.consentShown = await until(`document.querySelectorAll('[role=checkbox]').length === 2 && Boolean(${button})`);
  checks.disabledBeforeConsent = await evaluate(`(${button})?.getAttribute('aria-disabled') === 'true'`);
  await evaluate(`document.querySelectorAll('[role=checkbox]').forEach((box) => box.click())`);
  checks.checkedExposed = await until(`[...document.querySelectorAll('[role=checkbox]')].every((box) => box.getAttribute('aria-checked') === 'true')`);
  checks.clicked = await until(`(() => {
    const target = ${button};
    if (!target || target.getAttribute('aria-disabled') === 'true') return false;
    target.click();
    return true;
  })()`);
  checks.signedIn = await until(`Boolean(sessionStorage.getItem('pwm.session')) && location.pathname === '/'`);
  checks.verifierCleared = await evaluate(`sessionStorage.getItem('pwm.signin.verifier') === null`);
  checks.tokenNotInUrl = await evaluate(
    `!location.href.includes('code=') && !location.href.includes(sessionStorage.getItem('pwm.session'))`,
  );
  await send('Page.navigate', { url: new URL('/settings', appUrl).href });
  checks.accountShown = await until(`/Signed in with Google as/.test(document.body.innerText)`);
  socket.close();
} finally {
  chrome.kill();
  console.log(JSON.stringify(checks));
}
