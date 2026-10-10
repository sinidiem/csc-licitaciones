import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CSC — Sistema de Gestión de Licitaciones",
  description: "Gestión del ciclo comercial de licitaciones",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}