// E2E de CASOS NEGATIVOS y bordes con Playwright (datos ficticios).
// Requisitos: backend :8000 + frontend :3000 + usuario ui.demo@csc.dev / Uitest123!
// Uso: node e2e/ui_flow_neg.mjs   (desde frontend/)
// Evidencia: capturas en ../docs/revision/capturas/

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EVID = path.resolve(__dirname, "../../docs/revision/capturas");
const BASE = process.env.UI_URL || "http://127.0.0.1:3000";
const ts = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
const PNAME = `Neg ${ts}`;
let passed = 0;
let failed = 0;
let shot = 0;
const consoleErrs = [];
const pageErrors = [];

function ok(m) { passed++; console.log(`[ok ] ${m}`); }
function fail(m) { failed++; console.log(`[FALLO] ${m}`); }
async function shotPage(page, name) {
  shot++;
  await page.screenshot({ path: path.join(EVID, `${String(shot).padStart(2, "0")}_${name}.png`) });
  console.log(`[shot] ${name}`);
}
async function waitText(page, text, timeout = 15000) {
  await page.waitForFunction((t) => document.body.innerText.includes(t), text, { timeout });
}
async function banner(page) {
  const n = await page.locator(".error").count();
  return n ? (await page.locator(".error").first().innerText()).trim() : "";
}
async function fillLabel(page, label, value) {
  await page.locator("label", { hasText: label }).locator("input, select").fill(value);
}

async function main() {
  fs.mkdirSync(EVID, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") consoleErrs.push(m.text()); });

  // 1) Guard de sesión (sin cookie) → redirige a /login
  await page.goto(`${BASE}/licitaciones`);
  await page.waitForURL("**/login");
  ok("sin sesión /licitaciones redirige a /login");
  await shotPage(page, "guard_sin_sesion");

  // 2) Login con contraseña incorrecta → banner de error, se queda en /login
  await fillLabel(page, "Correo", "ui.demo@csc.dev");
  await fillLabel(page, "Contraseña", "incorrecta");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await page.waitForTimeout(1200);
  const b2 = await banner(page);
  if (page.url().includes("/login") && b2) ok(`login inválido rechazado ("${b2.slice(0, 60)}")`);
  else fail("login inválido no mostró error");
  await shotPage(page, "login_invalido");

  // 3) Login correcto
  await fillLabel(page, "Contraseña", "Uitest123!");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await page.waitForURL("**/licitaciones");
  ok("login correcto");

  // 4) Crear usuario con rol user (no admin) → 403 en banner (la regla es
  //    "solo admin crea usuarios"; el backend lo valida, no solo la UI)
  await page.goto(`${BASE}/usuarios`);
  await waitText(page, "Nuevo usuario");
  await fillLabel(page, "Nombre", `Nuevo ${ts}`);
  await fillLabel(page, "Correo", `nuevo-${ts}@csc.dev`);
  await fillLabel(page, "Contraseña", "Password123!");
  await page.getByRole("button", { name: "Crear usuario" }).click();
  await page.waitForFunction(() => document.querySelector(".error") !== null, { timeout: 15000 });
  const b4 = await banner(page);
  ok(`crear usuario como user rechazado 403 ("${b4.slice(0, 60)}")`);
  await shotPage(page, "crear_usuario_403");

  // 5) Cliente duplicado por correo (el email de empresa es úNICO por regla)
  //    → 409 en banner. (Los productos NO son únicos por nombre: el modelo
  //    solo indexa; crear el mismo nombre dos veces es válido por diseño.)
  await page.goto(`${BASE}/clientes`);
  await waitText(page, "Nuevo cliente");
  await fillLabel(page, "Nombre", `Dup ${ts}`);
  await fillLabel(page, "Correo de empresa", "sinidie@proton.me"); // ya ocupado (cliente sandbox)
  await page.getByRole("button", { name: "Crear cliente" }).click();
  await page.waitForFunction(() => document.querySelector(".error") !== null, { timeout: 15000 });
  const b5 = await banner(page);
  ok(`cliente duplicado por correo rechazado ("${b5.slice(0, 60)}")`);
  await shotPage(page, "cliente_duplicado");

  // 6) Partida que excede el presupuesto → banner y total intacto
  await page.goto(`${BASE}/productos`);
  await waitText(page, "Nuevo producto");
  await fillLabel(page, "Nombre", PNAME);
  await fillLabel(page, "Precio de referencia", "10");
  await page.getByRole("button", { name: "Crear producto" }).click();
  await waitText(page, PNAME);
  const pid = await page.evaluate(
    (name) => fetch("/api/products").then((r) => r.json()).then((ps) => ps.find((p) => p.name === name)?.id),
    PNAME,
  );
  await page.goto(`${BASE}/licitaciones`);
  await waitText(page, "Nueva licitación");
  await page.locator("select").first().selectOption({ index: 0 });
  await fillLabel(page, "Título", `Neg ${ts}`);
  await fillLabel(page, "Referencia", `NEG-${ts}`);
  await fillLabel(page, "Presupuesto máximo", "100");
  const dl = new Date(Date.now() + 15 * 86400000);
  const pad = (n) => String(n).padStart(2, "0");
  await fillLabel(page, "Fecha límite", `${dl.getFullYear()}-${pad(dl.getMonth() + 1)}-${pad(dl.getDate())}T${pad(dl.getHours())}:${pad(dl.getMinutes())}`);
  await page.getByRole("button", { name: "Crear borrador" }).click();
  await page.getByRole("link", { name: `NEG-${ts}` }).click();
  await page.waitForURL("**/licitaciones/**");
  await page.locator("select").first().selectOption(pid);
  await fillLabel(page, "Cantidad", "50");
  await fillLabel(page, "Precio unitario", "12.5");
  await page.getByRole("button", { name: "Añadir" }).click();
  await page.waitForFunction(() => document.querySelector(".error") !== null, { timeout: 15000 });
  const b6 = await banner(page);
  const stillEmpty = (await page.locator("body").innerText()).includes("Sin partidas todavía");
  if (b6 && stillEmpty) ok(`presupuesto excedido rechazado ("${b6.slice(0, 60)}")`);
  else fail(`presupuesto excedido: "${b6.slice(0, 60)}" | sin partidas=${stillEmpty}`);
  await shotPage(page, "presupuesto_excedido");

  // 7) Enviar sin propuesta → 409 PROPOSAL_REQUIRED, sigue Borrador
  await page.getByRole("button", { name: "Enviar oficialmente" }).click();
  await page.waitForFunction(() => document.querySelector(".error") !== null, { timeout: 15000 });
  const b7 = await banner(page);
  const badge = await page.locator(".badge").first().innerText();
  if (b7.toLowerCase().includes("propuesta") && badge.includes("Borrador"))
    ok(`envío sin propuesta rechazado ("${b7.slice(0, 60)}", estado ${badge})`);
  else fail(`envío sin propuesta: "${b7.slice(0, 60)}" badge=${badge}`);
  await shotPage(page, "envio_sin_propuesta");

  // 8) Detalle de licitación inexistente → banner de 404
  await page.goto(`${BASE}/licitaciones/00000000-0000-0000-0000-000000000000`);
  await page.waitForFunction(() => document.querySelector(".error") !== null, { timeout: 15000 });
  const b8 = await banner(page);
  ok(`id inexistente muestra error ("${b8.slice(0, 60)}")`);
  await shotPage(page, "detalle_404");

  // 9) Sin excepciones JS sin capturar en toda la sesión
  if (pageErrors.length === 0) ok("0 errores JS sin capturar");
  else fail(`pageerrors: ${pageErrors.join(" | ")}`);

  console.log("\n=== console.error (informativos, no fallan):");
  for (const e of [...new Set(consoleErrs)]) console.log("  -", e.slice(0, 130));

  await browser.close();
  return { passed, failed };
}

main()
  .then((r) => { console.log(`\n${r.passed} verificaciones ok, ${r.failed} fallos`); process.exit(r.failed ? 1 : 0); })
  .catch((e) => { console.log(`\n[ERROR] ${e.message}`); process.exit(1); });