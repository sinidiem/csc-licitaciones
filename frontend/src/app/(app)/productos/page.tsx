"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmt, type Product } from "@/lib/api";

export default function ProductosPage() {
  const [items, setItems] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      setItems(await api.products());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createProduct({
        name,
        default_unit_price: price,
        description: description || undefined,
      });
      setName("");
      setPrice("");
      setDescription("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Productos</h1>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <h2>Nuevo producto</h2>
        <form className="grid" onSubmit={create}>
          <label>
            Nombre
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
          </label>
          <label>
            Precio de referencia
            <input type="number" step="0.01" min="0" value={price} onChange={(e) => setPrice(e.target.value)} required />
          </label>
          <label>
            Descripción
            <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
          </label>
          <div className="row" style={{ alignItems: "end" }}>
            <button type="submit" disabled={busy}>{busy ? "Guardando…" : "Crear producto"}</button>
          </div>
        </form>
      </div>

      {!items ? (
        <div className="card muted">Cargando…</div>
      ) : items.length === 0 ? (
        <div className="card muted">Sin productos todavía.</div>
      ) : (
        <table>
          <thead>
            <tr><th>Nombre</th><th>Descripción</th><th className="num">Precio ref.</th><th>Estado</th></tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.description ?? "—"}</td>
                <td className="num">{fmt(p.default_unit_price)}</td>
                <td>{p.is_active ? "Activo" : "Inactivo"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}