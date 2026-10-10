"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function Nav() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    api
      .me()
      .then((u) => setIsAdmin(u.role === "admin"))
      .catch(() => {});
  }, []);

  async function logout() {
    try {
      await api.logout();
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <nav className="app-nav">
      <span className="brand">CSC</span>
      <Link href="/licitaciones">Licitaciones</Link>
      <Link href="/clientes">Clientes</Link>
      <Link href="/productos">Productos</Link>
      {isAdmin && <Link href="/usuarios">Usuarios</Link>}
      <span className="spacer" />
      <button className="logout" onClick={logout}>Cerrar sesión</button>
    </nav>
  );
}