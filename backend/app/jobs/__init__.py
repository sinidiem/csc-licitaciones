"""Tareas programadas: vencimiento y recordatorio ( §6).

El cron externo del VPS invoca un endpoint interno protegido por secreto
(POST /internal/jobs/tenders); la lógica de esas consultas y transiciones
idempotentes se implementa aquí en el día 8 del plan.
"""