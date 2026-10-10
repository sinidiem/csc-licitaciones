"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, fmt, STATUS_LABELS, type Client, type Tender } from "@/lib/api";

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function LicitacionesPage() {
  const [tenders, setTenders] = useState<Tender[] | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [clientId, setClientId] = useState("");
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [budget, setBudget] = useState("");
  // Vacío al hidratar: con Date.now() como valor inicial el SSR y el cliente
  // divergen → warning de hidratación de React. Se rellena en useEffect.
  const [deadline, setDeadline] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      const [ts, cs] = await Promise.all([api.tenders(), api.clients()]);
      setTenders(ts);
      setClients(cs);
      if (!clientId && cs.length > 0) setClientId(cs[0].id);
      if (!deadline) setDeadline(toLocalInput(new Date(Date.now() + 15 * 86400000).toISOString()));
    } catch (err) {
      setError((err as Error).message);
    }
  }, [clientId, deadline]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createTender({
        client_id: clientId,
        title,
        reference: reference || `LIC-${Date.now().toString().slice(-6)}`,
        deadline_at: new Date(deadline).toISOString(),
        budget_max: budget,
      });
      setTitle("");
      setReference("");
      setBudget("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Licitaciones</h1>
      {error && <div className="error">{error}</div>}
      {!tenders ? (
        <div className="card muted">Cargando…</div>
      ) : (
        <>
          <div className="card">
            <h2>Nueva licitación (borrador)</h2>
            <form className="grid" onSubmit={create}>
              <label>
                Cliente
                <select value={clientId} onChange={(e) => setClientId(e.target.value)} required>
                  {clients.length === 0 && <option value="">Sin clientes — créalos primero</option>}
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Título
                <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
              </label>
              <label>
                Referencia
                <input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={50} placeholder="LTC-2026-001" />
              </label>
              <label>
                Presupuesto máximo
                <input type="number" step="0.01" min="0.01" value={budget} onChange={(e) => setBudget(e.target.value)} required />
              </label>
              <label>
                Fecha límite
                <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} required />
              </label>
              <div className="row" style={{ alignItems: "end" }}>
                <button type="submit" disabled={busy || clients.length === 0}>
                  {busy ? "Creando…" : "Crear borrador"}
                </button>
              </div>
            </form>
          </div>

          {tenders.length === 0 ? (
            <div className="card muted">Aún no hay licitaciones.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Referencia</th>
                  <th>Título</th>
                  <th>Cliente</th>
                  <th>Estado</th>
                  <th className="num">Total</th>
                  <th className="num">Presupuesto</th>
                  <th>Fecha límite</th>
                </tr>
              </thead>
              <tbody>
                {tenders.map((t) => (
                  <tr key={t.id}>
                    <td><Link className="link" href={`/licitaciones/${t.id}`}>{t.reference ?? "—"}</Link></td>
                    <td>{t.title}</td>
                    <td>{t.client_name}</td>
                    <td><span className={`badge badge-${t.status}`}>{STATUS_LABELS[t.status] ?? t.status}</span></td>
                    <td className="num">{fmt(t.total)}</td>
                    <td className="num">{fmt(t.budget_max)}</td>
                    <td>{new Date(t.deadline_at).toLocaleDateString("es-ES")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}