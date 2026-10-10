"""Servicios de dominio: transiciones, presupuesto, pagos, outbox.

Aquí viven las reglas de negocio (matriz de transiciones, saldo, validación
de presupuesto en transacción) y las integraciones externas (Resend,
Supabase Storage). Se implementan en los días 4-8 del plan.
"""