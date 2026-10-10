// Cliente de la API: habla con /api/* (rewrite de Next hacia el backend).
// La sesión vive en cookie HttpOnly; `credentials: same-origin` la envía.

export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
}

export interface Client {
  id: string;
  name: string;
  company_email: string;
  contact_name: string | null;
  contact_phone: string | null;
  address: string | null;
}

export interface Product {
  id: string;
  name: string;
  description: string | null;
  default_unit_price: string;
  is_active: boolean;
}

export interface TenderItem {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

export interface TenderPayment {
  id: string;
  amount: string;
  paid_at: string;
  reference: string | null;
  notes: string | null;
}

export interface TenderHistory {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  source: string;
  actor_user_id: string | null;
  created_at: string;
}

export interface Tender {
  id: string;
  client_id: string;
  client_name: string;
  company_email: string;
  title: string;
  reference: string | null;
  description: string | null;
  status: string;
  budget_max: string;
  total: string;
  deadline_at: string;
  invoiced_total: string | null;
  saldo_pendiente: string | null;
  reminder_sent_at: string | null;
  submitted_at: string | null;
  proposal_file_id: string | null;
  proposal_name: string | null;
  created_at: string;
  items: TenderItem[];
  payments: TenderPayment[];
  history: TenderHistory[];
}

export const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  active: "Activa",
  finished: "Finalizada",
  to_collect: "Por cobrar",
  collected: "Cobrada",
  lost: "Perdida",
};

export type ApiError = Error & { status?: number };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...options,
    headers: isForm ? (options.headers as HeadersInit) : {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let message = `Error ${res.status}`;
    try {
      const data = await res.json();
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        // Errores de validación pydantic: detail es [{msg, ...}]
        message = detail[0]?.msg ?? message;
      } else {
        message = typeof detail === "string" ? detail : (detail?.message ?? message);
      }
    } catch {
      /* cuerpo no JSON */
    }
    // Sesión caducada o inválida: fuera de la pantalla de login, volver
    // a /login en lugar de dejar banners 401 página por página.
    if (res.status === 401 && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    const err = new Error(message) as ApiError;
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) =>
    request<{ message: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),

  users: () => request<User[]>("/users"),
  createUser: (data: { name: string; email: string; password: string; role: string }) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(data) }),

  clients: () => request<Client[]>("/clients"),
  createClient: (data: Partial<Client>) =>
    request<Client>("/clients", { method: "POST", body: JSON.stringify(data) }),
  updateClient: (id: string, data: Partial<Client>) =>
    request<Client>(`/clients/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteClient: (id: string) => request<Client>(`/clients/${id}`, { method: "DELETE" }),

  products: () => request<Product[]>("/products"),
  createProduct: (data: { name: string; default_unit_price: string; description?: string }) =>
    request<Product>("/products", { method: "POST", body: JSON.stringify(data) }),

  tenders: () => request<Tender[]>("/tenders?limit=100"),
  tender: (id: string) => request<Tender>(`/tenders/${id}`),
  createTender: (data: {
    client_id: string;
    title: string;
    reference: string;
    deadline_at: string;
    budget_max: string;
    description?: string;
  }) => request<Tender>("/tenders/", { method: "POST", body: JSON.stringify(data) }),

  addItem: (id: string, data: { product_id: string; quantity: number; unit_price: string }) =>
    request<TenderItem>(`/tenders/${id}/items`, { method: "POST", body: JSON.stringify(data) }),
  removeItem: (id: string, itemId: string) =>
    request<void>(`/tenders/${id}/items/${itemId}`, { method: "DELETE" }),

  uploadProposal: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Tender>(`/tenders/${id}/proposal`, { method: "POST", body: fd });
  },
  send: (id: string) => request<Tender>(`/tenders/${id}/send`, { method: "POST", body: "{}" }),
  finish: (id: string, reason?: string) =>
    request<Tender>(`/tenders/${id}/transitions/finish`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }),
  lose: (id: string, reason?: string) =>
    request<Tender>(`/tenders/${id}/transitions/lose`, { method: "POST", body: JSON.stringify({ reason: reason || null }) }),
  invoice: (id: string, invoiced_total: string) =>
    request<Tender>(`/tenders/${id}/invoice`, { method: "POST", body: JSON.stringify({ invoiced_total }) }),
  pay: (id: string, amount: string, reference?: string) =>
    request<Tender>(`/tenders/${id}/payments`, { method: "POST", body: JSON.stringify({ amount, reference: reference || null }) }),
};

export function fmt(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(value);
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return d.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });
}