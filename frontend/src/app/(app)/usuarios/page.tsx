"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type User } from "@/lib/api";

export default function UsuariosPage() {
  const [items, setItems] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");

  const load = useCallback(async () => {
    try {
      setError(null);
      setItems(await api.users());
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
      await api.createUser({ name, email, password, role });
      setName("");
      setEmail("");
      setPassword("");
      setRole("user");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>Usuarios</h1>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <h2>Nuevo usuario</h2>
        <p className="muted">Solo un administrador puede crear usuarios (el backend lo valida).</p>
        <form className="grid" onSubmit={create}>
          <label>
            Nombre
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={150} />
          </label>
          <label>
            Correo
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Contraseña
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </label>
          <label>
            Rol
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <div className="row" style={{ alignItems: "end" }}>
            <button type="submit" disabled={busy}>{busy ? "Guardando…" : "Crear usuario"}</button>
          </div>
        </form>
      </div>

      {!items ? (
        <div className="card muted">Cargando…</div>
      ) : (
        <table>
          <thead>
            <tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Activo</th></tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td>
                <td>{u.email}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? "Sí" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}