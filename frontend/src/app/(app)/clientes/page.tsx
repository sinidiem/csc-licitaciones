"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Client } from "@/lib/api";

export default function ClientesPage() {
  const [items, setItems] = useState<Client[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [contact, setContact] = useState("");
  const [phone, setPhone] = useState("");

  // Edición inline (formulario reutilizado con los datos del cliente)
  const [editing, setEditing] = useState<Client | null>(null);
  const [eName, setEName] = useState("");
  const [eEmail, setEEmail] = useState("");
  const [eContact, setEContact] = useState("");
  const [ePhone, setEPhone] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      setItems(await api.clients());
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
      await api.createClient({
        name,
        company_email: email,
        contact_name: contact || null,
        contact_phone: phone || null,
      });
      setName("");
      setEmail("");
      setContact("");
      setPhone("");
      setOk("Cliente creado.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(c: Client) {
    setEditing(c);
    setEName(c.name);
    setEEmail(c.company_email);
    setEContact(c.contact_name ?? "");
    setEPhone(c.contact_phone ?? "");
    setError(null);
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateClient(editing.id, {
        name: eName,
        company_email: eEmail,
        contact_name: eContact || null,
        contact_phone: ePhone || null,
      });
      setOk("Cliente actualizado.");
      setEditing(null);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(c: Client) {
    if (!window.confirm(`¿Eliminar al cliente "${c.name}"? Sus licitaciones se conservan, pero dejará de aparecer en las listas.`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteClient(c.id);
      setOk(`Cliente "${c.name}" eliminado (borrado lógico).`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Clientes</h1>
      {error && <div className="error">{error}</div>}
      {ok && <div className="success">{ok}</div>}

      <div className="card">
        <h2>{editing ? `Editar cliente: ${editing.name}` : "Nuevo cliente"}</h2>
        <form
          className="grid"
          onSubmit={editing ? saveEdit : create}
        >
          <label>
            Nombre
            <input
              value={editing ? eName : name}
              onChange={(e) => (editing ? setEName(e.target.value) : setName(e.target.value))}
              required maxLength={200}
            />
          </label>
          <label>
            Correo de empresa
            <input
              type="email"
              value={editing ? eEmail : email}
              onChange={(e) => (editing ? setEEmail(e.target.value) : setEmail(e.target.value))}
              required
            />
          </label>
          <label>
            Contacto
            <input
              value={editing ? eContact : contact}
              onChange={(e) => (editing ? setEContact(e.target.value) : setContact(e.target.value))}
              maxLength={150}
            />
          </label>
          <label>
            Teléfono
            <input
              value={editing ? ePhone : phone}
              onChange={(e) => (editing ? setEPhone(e.target.value) : setPhone(e.target.value))}
              maxLength={50}
            />
          </label>
          <div className="row" style={{ alignItems: "end" }}>
            {editing ? (
              <>
                <button type="submit" disabled={busy}>{busy ? "Guardando…" : "Guardar cambios"}</button>
                <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
              </>
            ) : (
              <button type="submit" disabled={busy}>{busy ? "Guardando…" : "Crear cliente"}</button>
            )}
          </div>
        </form>
      </div>

      {!items ? (
        <div className="card muted">Cargando…</div>
      ) : items.length === 0 ? (
        <div className="card muted">Sin clientes todavía.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Contacto</th>
              <th>Teléfono</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.company_email}</td>
                <td>{c.contact_name ?? "—"}</td>
                <td>{c.contact_phone ?? "—"}</td>
                <td className="row" style={{ gap: 8 }}>
                  <button onClick={() => startEdit(c)}>Editar</button>
                  <button className="danger" onClick={() => remove(c)} disabled={busy}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}