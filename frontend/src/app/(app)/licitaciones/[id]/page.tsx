"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, fmt, fmtDate, STATUS_LABELS, type Product, type Tender } from "@/lib/api";

export default function LicitacionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [tender, setTender] = useState<Tender | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Formularios
  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [invoiceAmount, setInvoiceAmount] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [payRef, setPayRef] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [t, ps] = await Promise.all([api.tender(id), api.products()]);
      setTender(t);
      setProducts(ps);
      if (ps.length > 0) {
        setProductId(ps[0].id);
        setPrice(t.status === "draft" && ps[0] ? ps[0].default_unit_price : "");
      }
      if (t.invoiced_total === null && t.status === "finished") setInvoiceAmount(t.total);
      if (t.saldo_pendiente !== null && t.status === "to_collect") setPayAmount(t.saldo_pendiente);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>, success?: string) {
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      await action();
      if (success) setOk(success);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!tender) {
    return (
      <div>
        <div className="card muted">Cargando licitación…</div>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  const s = tender.status;
  const canPay = s === "to_collect";
  const saldo = tender.saldo_pendiente;

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await run(() => api.uploadProposal(id, file), "Propuesta subida.");
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <h1 style={{ margin: 0 }}>{tender.title}</h1>
        <span className={`badge badge-${s}`}>{STATUS_LABELS[s] ?? s}</span>
        <span className="muted">{tender.reference}</span>
      </div>

      {error && <div className="error">{error}</div>}
      {ok && <div className="success">{ok}</div>}

      <div className="detail-grid">
        <div>
          <div className="card">
            <h2>Datos generales</h2>
            <table>
              <tbody>
                <tr><th>Cliente</th><td>{tender.client_name} <span className="muted">({tender.company_email})</span></td></tr>
                <tr><th>Total partidas</th><td className="num">{fmt(tender.total)}</td></tr>
                <tr><th>Presupuesto máximo</th><td className="num">{fmt(tender.budget_max)}</td></tr>
                <tr><th>Fecha límite</th><td>{fmtDate(tender.deadline_at)}</td></tr>
                <tr><th>Enviada</th><td>{fmtDate(tender.submitted_at)}</td></tr>
                <tr><th>Facturado</th><td className="num">{fmt(tender.invoiced_total)}</td></tr>
                <tr><th>Saldo pendiente</th><td className="num">{fmt(saldo)}</td></tr>
                {tender.reminder_sent_at && (
                  <tr><th>Recordatorio 48h</th><td>{fmtDate(tender.reminder_sent_at)}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="row">
              <h2 style={{ margin: 0 }}>Partidas</h2>
              <span className="spacer" style={{ flex: 1 }} />
              <span className="muted">Total: <strong>{fmt(tender.total)}</strong></span>
            </div>
            <table>
              <thead>
                <tr><th>Producto</th><th className="num">Cantidad</th><th className="num">Precio unit.</th><th className="num">Subtotal</th><th /></tr>
              </thead>
              <tbody>
                {tender.items.map((i) => (
                  <tr key={i.id}>
                    <td>{i.product_name}</td>
                    <td className="num">{i.quantity}</td>
                    <td className="num">{fmt(i.unit_price)}</td>
                    <td className="num">{fmt(i.subtotal)}</td>
                    <td>
                      {s === "draft" && (
                        <button className="danger" disabled={busy} onClick={() => run(() => api.removeItem(id, i.id))}>Quitar</button>
                      )}
                    </td>
                  </tr>
                ))}
                {tender.items.length === 0 && (
                  <tr><td colSpan={4} className="muted">Sin partidas todavía.</td></tr>
                )}
              </tbody>
            </table>

            {s === "draft" && (
              <form
                className="grid"
                style={{ marginTop: 14 }}
                onSubmit={(e) => {
                  e.preventDefault();
                  run(() => api.addItem(id, { product_id: productId, quantity: Number(qty), unit_price: price }), "Partida añadida.");
                }}
              >
                <label>
                  Producto
                  <select value={productId} onChange={(e) => {
                    setProductId(e.target.value);
                    const p = products.find((x) => x.id === e.target.value);
                    if (p) setPrice(p.default_unit_price);
                  }}>
                    {products.length === 0 && <option value="">Sin productos</option>}
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} ({fmt(p.default_unit_price)})</option>
                    ))}
                  </select>
                </label>
                <label>
                  Cantidad
                  <input type="number" min="1" step="1" value={qty} onChange={(e) => setQty(e.target.value)} required />
                </label>
                <label>
                  Precio unitario
                  <input type="number" step="0.01" min="0" value={price} onChange={(e) => setPrice(e.target.value)} required />
                </label>
                <div className="row" style={{ alignItems: "end" }}>
                  <button type="submit" disabled={busy || products.length === 0}>Añadir</button>
                </div>
              </form>
            )}
            {s !== "draft" && <p className="muted">Partidas congeladas: solo se editan en borrador.</p>}
          </div>

          <div className="card">
            <h2>Propuesta</h2>
            <div className="row">
              {tender.proposal_name ? (
                <>
                  <span>{tender.proposal_name}</span>
                  <a className="link" href={`/api/tenders/${id}/proposal/download`} target="_blank" rel="noopener noreferrer">
                    Descargar
                  </a>
                </>
              ) : (
                <span className="muted">Sin propuesta adjunta.</span>
              )}
              {s === "draft" && (
                <>
                  <span className="spacer" style={{ flex: 1 }} />
                  <label className="muted" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <input ref={fileInput} type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.odt,.txt" onChange={onUpload} disabled={busy} />
                    Subir propuesta (PDF/DOC/XLS, máx 10 MB)
                  </label>
                </>
              )}
            </div>
          </div>

          <div className="card">
            <h2>Acciones</h2>
            <div className="row">
              {s === "draft" && (
                <button disabled={busy} onClick={() => run(() => api.send(id), "Enviada. Se envió el correo oficial con la propuesta.")}>
                  Enviar oficialmente
                </button>
              )}
              {s === "active" && (
                <>
                  <button disabled={busy} onClick={() => run(() => api.finish(id), "Finalizada.")}>Finalizar (ganada)</button>
                  <button className="danger" disabled={busy} onClick={() => run(() => api.lose(id), "Marcada como perdida.")}>
                    Marcar perdida
                  </button>
                </>
              )}
              {s === "finished" && (
                <form className="row" onSubmit={(e) => {
                  e.preventDefault();
                  run(() => api.invoice(id, invoiceAmount), "Factura registrada.");
                }}>
                  <label>
                    Importe facturado
                    <input type="number" step="0.01" min="0.01" value={invoiceAmount} onChange={(e) => setInvoiceAmount(e.target.value)} required />
                  </label>
                  <button type="submit" disabled={busy}>Facturar</button>
                </form>
              )}
              {canPay && (
                <form className="row" onSubmit={(e) => {
                  e.preventDefault();
                  run(() => api.pay(id, payAmount, payRef), "Pago registrado.");
                }}>
                  <label>
                    Importe
                    <input type="number" step="0.01" min="0.01" max={saldo ?? undefined} value={payAmount} onChange={(e) => setPayAmount(e.target.value)} required />
                  </label>
                  <label>
                    Referencia
                    <input value={payRef} onChange={(e) => setPayRef(e.target.value)} maxLength={100} placeholder="TRF-…" />
                  </label>
                  <button type="submit" disabled={busy}>Registrar pago</button>
                </form>
              )}
              {(s === "lost" || s === "collected") && <span className="muted">Estado terminal: sin acciones.</span>}
            </div>
          </div>
        </div>

        <div>
          <div className="card">
            <h2>Pagos</h2>
            {tender.payments.length === 0 ? (
              <span className="muted">Sin pagos.</span>
            ) : (
              <table>
                <thead>
                  <tr><th className="num">Importe</th><th>Fecha</th><th>Ref.</th></tr>
                </thead>
                <tbody>
                  {tender.payments.map((p) => (
                    <tr key={p.id}>
                      <td className="num">{fmt(p.amount)}</td>
                      <td>{fmtDate(p.paid_at)}</td>
                      <td>{p.reference ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {s === "to_collect" && (
              <p className="muted">Saldo pendiente: <strong>{fmt(saldo)}</strong></p>
            )}
          </div>

          <div className="card">
            <h2>Historial</h2>
            {tender.history.map((h, i) => (
              <div key={i} className={`history-item ${h.source === "system" ? "system" : ""}`}>
                <strong>{h.from_status ? STATUS_LABELS[h.from_status] : "Inicio"} → {STATUS_LABELS[h.to_status]}</strong>
                <div className="muted">{fmtDate(h.created_at)} · {h.source === "system" ? "sistema" : "usuario"}{h.reason ? ` · ${h.reason}` : ""}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="muted" style={{ marginBottom: 24 }}>
        <Link className="link" href="/licitaciones">← Volver a licitaciones</Link>
      </div>
    </div>
  );
}