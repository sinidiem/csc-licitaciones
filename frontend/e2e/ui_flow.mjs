// E2E del flujo completo de la UI con Playwright (datos ficticios).
// Requisitos: backend en :8000 y frontend en :3000, usuario fixture
// ui.demo@csc.dev (usuario de prueba del admin).
// Uso: node e2e/ui_flow.mjs   (desde frontend/)
// Evidencia: capturas y propuesta en ../docs/evidencias/dia10_ui/

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EVID = path.resolve(__dirname, "../../docs/evidencias/dia10_ui");
const BASE = process.env.UI_URL || "http://127.0.0.1:3000";
const EMAIL = process.env.UI_USER || "ui.demo@csc.dev";
const PASS = process.env.UI_PASS || "Uitest123!";

const ts = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
const uniq = `E2E-${ts}`;
const CLIENT = `Cliente UI ${uniq}`;
const PRODUCT = `Servicio UI ${uniq}`;
const REF = `LTC-${ts}`;
const TITLE = `Licitación UI ${uniq}`;
const PRICE = "12.50";
const QTY = "50";
const TOTAL = "625.00"; // 50 × 12.50
const PROPOSAL_FILE = path.join(EVID, `propuesta_${uniq}.txt`);
const SANDBOX_EMAIL = "sinidie@proton.me";

let passed = 0;
let failed = 0;
let shot = 0;

function ok(msg) {
  passed++;
  console.log(`[ok ] ${msg}`);
}
function fail(msg) {
  failed++;
  console.log(`[FALLO] ${msg}`);
}

async function shotPage(page, name) {
  shot++;
  const p = path.join(EVID, `${String(shot).padStart(2, "0")}_${name}.png`);
  await page.screenshot({ path: p });
  console.log(`[shot] ${p}`);
}

async function waitText(page, text, timeout = 20000) {
  await page.waitForFunction(
    (t) => document.body.innerText.includes(t),
    text,
    { timeout },
  );
}

async function fillLabel(page, label, value) {
  await page.locator("label", { hasText: label }).locator("input, select").fill(value);
}

async function main() {
  fs.mkdirSync(EVID, { recursive: true });
  fs.writeFileSync(
    PROPOSAL_FILE,
    `Propuesta de prueba E2E — datos ficticios\nCliente: ${CLIENT}\nReferencia: ${REF}\nGenerado: ${new Date().toISOString()}\n`,
  );

  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(20000);
  const results = { ok: [], fail: [] };

  // 1) Login
  await page.goto(`${BASE}/login`);
  await waitText(page, "CSC — Licitaciones");
  await fillLabel(page, "Correo", EMAIL);
  await fillLabel(page, "Contraseña", PASS);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await page.waitForURL("**/licitaciones");
  ok("login -> /licitaciones");
  await shotPage(page, "login_lista");

  // 2) Cliente sandbox (reutilizar si existe — el correo es único y es el
  //    único destinatario que el sandbox de Resend entrega de verdad)
  let clientName = CLIENT;
  const clients = await page.evaluate(() => fetch("/api/clients").then((r) => r.json()));
  const sandbox = clients.find((c) => c.company_email === SANDBOX_EMAIL);
  if (sandbox) {
    clientName = sandbox.name;
    ok(`cliente sandbox reutilizado: ${clientName}`);
  } else {
    await page.goto(`${BASE}/clientes`);
    await waitText(page, "Nuevo cliente");
    await fillLabel(page, "Nombre", CLIENT);
    await fillLabel(page, "Correo de empresa", "sinidie@proton.me");
    await page.getByRole("button", { name: "Crear cliente" }).click();
    await waitText(page, CLIENT);
    ok(`cliente creado: ${CLIENT}`);
    await shotPage(page, "clientes");
  }

  // 3) Crear producto
  await page.goto(`${BASE}/productos`);
  await waitText(page, "Nuevo producto");
  await fillLabel(page, "Nombre", PRODUCT);
  await fillLabel(page, "Precio de referencia", PRICE);
  await page.getByRole("button", { name: "Crear producto" }).click();
  await waitText(page, PRODUCT);
  ok(`producto creado: ${PRODUCT} (${PRICE})`);

  // 4) Crear borrador de licitación
  await page.goto(`${BASE}/licitaciones`);
  await waitText(page, "Nueva licitación");
  await page.locator("select").first().selectOption({ label: clientName });
  await fillLabel(page, "Título", TITLE);
  await fillLabel(page, "Referencia", REF);
  await fillLabel(page, "Presupuesto máximo", "10000");
  const dl = new Date(Date.now() + 30 * 86400000);
  const pad = (n) => String(n).padStart(2, "0");
  await fillLabel(page, "Fecha límite", `${dl.getFullYear()}-${pad(dl.getMonth() + 1)}-${pad(dl.getDate())}T${pad(dl.getHours())}:${pad(dl.getMinutes())}`);
  await page.getByRole("button", { name: "Crear borrador" }).click();
  await page.getByRole("link", { name: REF }).click();
  await page.waitForURL("**/licitaciones/**");
  await waitText(page, "Sin partidas todavía");
  ok(`borrador creado y abierto: ${REF}`);
  await shotPage(page, "detalle_borrador");

  // 5) Añadir partida y comprobar total
  const productId = await page.evaluate(
    (name) =>
      fetch("/api/products")
        .then((r) => r.json())
        .then((ps) => ps.find((p) => p.name === name)?.id),
    PRODUCT,
  );
  if (!productId) throw new Error(`producto "${PRODUCT}" no encontrado en la API`);
  await page.locator("select").first().selectOption(productId);
  await fillLabel(page, "Cantidad", QTY);
  await fillLabel(page, "Precio unitario", PRICE);
  await page.getByRole("button", { name: "Añadir" }).click();
  await waitText(page, TOTAL.replace(".", ","));
  ok(`partida añadida; total ${TOTAL}`);
  await shotPage(page, "detalle_partida");

  // 6) Subir propuesta
  await page.setInputFiles("input[type=file]", PROPOSAL_FILE);
  await waitText(page, "Propuesta subida");
  ok("propuesta subida al bucket (URL firmada en descarga)");
  await shotPage(page, "detalle_propuesta");

  // 7) Enviar (correo REAL de Resend con el adjunto desde Supabase)
  await page.getByRole("button", { name: "Enviar oficialmente" }).click();
  await waitText(page, "Enviada");
  await waitText(page, "Activa");
  ok("enviada -> estado Activa (correo Resend real disparado)");
  await shotPage(page, "tras_envio");

  // 8) Finalizar (ganada)
  await page.getByRole("button", { name: "Finalizar (ganada)" }).click();
  await waitText(page, "Finalizada");
  ok("finalizada (ganada)");

  // 9) Facturar (importe = total de partidas)
  await fillLabel(page, "Importe facturado", TOTAL);
  await page.getByRole("button", { name: "Facturar" }).click();
  await waitText(page, "Factura registrada");
  await waitText(page, "Por cobrar");
  ok(`facturada ${TOTAL} -> Por cobrar`);

  // 10) Registrar pago por importe total -> Cobrada
  await fillLabel(page, "Importe", TOTAL);
  await fillLabel(page, "Referencia", `TRF-${uniq}`);
  await page.getByRole("button", { name: "Registrar pago" }).click();
  await waitText(page, "Pago registrado");
  await waitText(page, "Cobrada");
  ok("pago total -> Cobrada (saldo 0)");
  await shotPage(page, "cobrada");

  // 11) Historial completo
  const history = await page.locator(".history-item").allInnerTexts();
  const joined = history.join("\n");
  for (const step of ["Borrador → Activa", "Activa → Finalizada", "Finalizada → Por cobrar", "Por cobrar → Cobrada"]) {
    if (joined.includes(step)) ok(`historial: ${step}`);
    else fail(`historial sin: ${step}`);
  }
  await page.getByRole("link", { name: "← Volver a licitaciones" }).click();
  await waitText(page, REF);
  ok("licitación visible en el listado");
  await shotPage(page, "lista_final");

  await browser.close();
  return { passed, failed, shot };
}

main()
  .then((r) => {
    console.log(`\n${r.passed} verificaciones ok, ${r.failed} fallos, ${r.shot} capturas en ${EVID}`);
    process.exit(r.failed ? 1 : 0);
  })
  .catch((e) => {
    console.log(`\n[ERROR] ${e.message}`);
    process.exit(1);
  });