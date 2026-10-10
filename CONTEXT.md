# CSC - CONSULTORIA Y SOLUCIONES CABALLERO
## Prueba Técnica: Desarrollador Jr/Mid
### Sistema de Gestión de Licitaciones
**Tiempo estimado de entrega:** 10 días

---

## Contexto del Negocio
Una empresa necesita administrar licitaciones comerciales para sus clientes. Cada licitación pertenece a un cliente, contiene productos que la empresa planea vender, requiere un documento de propuesta formal, y debe enviarse oficialmente a la empresa cliente antes de que el plazo de presentación corra.

### Tecnologías permitidas
Next.js, Python (Django/FastAPI), React, Vue, Angular, Laravel, Spring Boot, Node.js, Hono.js-full-stack o backend/frontend separado.

### Integraciones obligatorias:
* **Proveedor de email transaccional real** (Resend, SendGrid, o similar con plan gratuito), con soporte de adjuntos.
* **Servicio de almacenamiento de archivos real** (S3, Cloudinary, o Supabase Storage, Upload Thing) para el documento de la propuesta.
* **Mecanismo de tarea programada** (cron, BullMQ + Redis, Celery beat, o cron externo) para el vencimiento automático y el recordatorio.
* **Base de datos:** PostgreSQL corriendo en Docker o Supabase.

---

## Relaciones entre Entidades
* Un Cliente puede tener múltiples Licitaciones.
* Una Licitación pertenece a un solo Cliente.
* Una Licitación puede contener múltiples Productos (N:M, con cantidad y precio).
* Una Licitación tiene un documento de propuesta adjunto (referencia/URL del archivo subido).
* Una Licitación puede tener múltiples Pagos registrados (cuando está en estado `por_cobrar`).
* Cada cambio de estado de una Licitación genera un registro en el Historial de Transiciones (estado anterior, estado nuevo, usuario, fecha/hora).

---

## Acceso y Seguridad
* Login email/password, roles base (`admin`/`user`), JWT/Cookies.
* Auditoría (quién creó/modificó y cuándo) en cada entidad.
* Solo los admins pueden crear otros usuarios.

---

## Estados de la Licitación y Tabla de Transiciones
**Estados:** `activa`, `finalizada`, `por_cobrar`, `cobrada`, `perdida`.

### Transiciones válidas (cualquier otra combinación debe rechazarse con error):
1. **borrador** (implícito, antes de enviar) $\rightarrow$ **activa**: solo se permite si la licitación tiene documento de propuesta adjunto. Dispara el correo al cliente.
2. **activa** $\rightarrow$ **finalizada**: la empresa ganó y completó la entrega.
3. **activa** $\rightarrow$ **perdida**: manual (no se ganó la licitación) o automática (se venció la fecha límite sin resolución).
4. **finalizada** $\rightarrow$ **por_cobrar**: se facturó, queda pendiente el cobro.
5. **por_cobrar** $\rightarrow$ **cobrada**: automática, cuando el saldo pendiente llega a cero tras los pagos registrados.

> Una licitación en `finalizada`, `por_cobrar`, `cobrada` o `perdida` no debe permitir agregar o quitar productos.

---

## Reglas de Negocio Principal
1. El total de productos asociados a una licitación no debe superar su presupuesto máximo; si se excede, la API retorna error.
2. Toda licitación tiene una `fecha_límite`. Si pasa la fecha límite y la licitación sigue en estado **activa**, el sistema la transiciona automáticamente a **perdida** (job/chequeo programado).
3. Una licitación solo puede enviarse (pasar a **activa**) si tiene un documento de propuesta adjunto subido al servicio de almacenamiento.
4. Al enviarse (transición a **activa**), el sistema envía automáticamente un correo real a la empresa cliente con el resumen de la licitación (productos, presupuesto, fecha límite) y el documento adjunto.
5. Si la licitación sigue **activa** y faltan menos de 48 horas para la fecha límite, el sistema envía un correo de recordatorio a la empresa cliente (mismo mecanismo programado que el punto 2).
6. En estado **por_cobrar** se pueden registrar pagos contra la licitación. El saldo pendiente es el total facturado menos la suma de pagos; no se puede registrar un pago mayor al saldo pendiente. Al llegar el saldo a cero, la licitación pasa automáticamente a **cobrada**.
7. Toda transición de estado debe quedar registrada en el historial (usuario, fecha, estado anterior/nuevo); solo se permiten las transiciones de la tabla anterior.

---

## API Mínimo Esperado
* **Clientes:** Creación y listado.
* **Usuarios:** Creación y listado.
* **Productos:** Creación y listado.
* **Licitaciones:** Creación (`borrador`), listado, detalle (datos generales, productos, historial de estado), agregar/quitar productos (solo si editable), subir documento de propuesta, enviar (valida documento, dispara correo, transiciona a `activa`), marcar `finalizada`/`perdida`, registrar pago (solo si `por_cobrar`), historial de transiciones.

---

## Requisitos Técnicos
* PostgreSQL Dockerizado o Supabase.
* Integración real de email con adjuntos (no simulada con `console.log`).
* Integración real de almacenamiento de archivos, con el documento accesible vía URL real.
* Job o chequeo programado funcionando en el ambiente desplegado (no solo en local) para vencimiento y recordatorio.

---

## Entregables
* Repositorio Git público, README con instrucciones de instalación y ejecución.
* Despliegue en servicio gratuito (Vercel, Render, Netlify) con enlace funcional.
* Evidencia de un correo real recibido por el cliente con el documento adjunto (captura o log del proveedor).
* Evidencia de que el documento subido es accesible vía URL real.

---

## Funcionalidades Extra
* Swagger/OpenAPI si el API es independiente del frontend.
* Panel simple de licitaciones próximas a vencer (activas con fecha límite cercana).

---

## Criterios de Evaluación
* Diseño del modelo de datos.
* Claridad de arquitectura.
* Organización del código.
* Manejo de reglas de negocio.
* Documentación, Despliegue funcional.
* Manejo de lógica basada en tiempo (vencimiento automático + recordatorio).
* Integración real de email con adjuntos.
* Integración real de almacenamiento de archivos.

---

## Resultado Esperado
Una aplicación funcional donde una licitación se redacta, se le adjunta una propuesta, se envía formalmente al cliente con notificación automática, se le da seguimiento hasta su fecha límite con recordatorios, se resuelve (ganada o perdida) y, si se ganó, se factura y cobra hasta saldar, todo auditado paso a paso y desplegado para que un usuario final pueda probarlo de principio a fin.


# Plan de desarrollo — Sistema de Gestión de Licitaciones

**Documento base para mantener contexto durante el desarrollo**  
**Fuente de requisitos:** `Prueba Técnica v2_261006_084559.pdf` (documento entregado por el usuario).  
**Fecha de preparación:** 6 de octubre de 2026.  
**Estado:** plan inicial; las decisiones marcadas como propuestas deben confirmarse o reemplazarse al iniciar la implementación.

## 1. Propósito y alcance

Construir una aplicación web desplegada y utilizable de extremo a extremo para gestionar el ciclo comercial de una licitación: redactar borrador, asociar productos, adjuntar propuesta, enviarla oficialmente al cliente, controlar vencimiento y recordatorio, registrar resultado, facturar y registrar pagos. Las acciones y cambios de estado deben quedar auditados.

El PDF es la fuente de requisitos del producto/evaluación, no una lista de acciones que deban ejecutarse en este documento. Este plan traduce esos requisitos a trabajo implementable. No se ha desplegado ni integrado ningún servicio todavía.

### Dentro del alcance obligatorio

- Autenticación email/contraseña, roles `admin` y `user`; solo `admin` crea usuarios.
- CRUD mínimo de clientes, productos y licitaciones, con listado y detalle.
- Licitación borrador con presupuesto máximo, fecha límite, cliente y partidas producto/cantidad/precio.
- Carga de propuesta a almacenamiento real y acceso por URL.
- Envío de correo real con resumen y adjunto al activar una licitación.
- Transiciones controladas y registro histórico de cada transición.
- Vencimiento automático de licitaciones activas y recordatorio dentro de las últimas 48 horas.
- Facturación y pagos parciales; impedir sobrepago y pasar automáticamente a `cobrada` al saldar.
- Despliegue público funcional, documentación de instalación/uso y evidencia real de email y archivo.

### Fuera del alcance inicial (salvo que se solicite)

Multiempresa/tenancy, aprobaciones, firma electrónica, generación automática de PDF, facturación fiscal, monedas múltiples, recuperación MFA/SSO, notificaciones distintas al correo, permisos granulares, reportes avanzados y aplicación móvil.

## 2. Decisiones técnicas propuestas

| Área | Propuesta inicial | Motivo / condición |
|---|---|---|
| Frontend | Next.js + TypeScript | UI y despliegue sencillos; formularios y panel en una sola app. |
| Backend | FastAPI + Pydantic, API REST | Separación clara de reglas de negocio y OpenAPI/Swagger generado. |
| Persistencia | PostgreSQL en Docker para desarrollo; PostgreSQL administrado para despliegue | El mismo motor en ambos ambientes y despliegue viable. |
| ORM/migraciones | SQLAlchemy 2 + Alembic | Modelado explícito y cambios versionados. |
| Sesión | JWT en cookie `HttpOnly`, `Secure` en producción, `SameSite` adecuado; contraseñas con Argon2id | Evita guardar tokens en `localStorage`; revisar protección CSRF según diseño de cookie. |
| Archivos | Supabase Storage o S3 compatible, mediante bucket privado | URL firmada para descarga; validar extensión, tamaño y MIME. Evitar URL pública permanente con propuestas comerciales. |
| Email | Resend con adjunto | Proveedor real; almacenar el resultado/ID del envío y gestionar fallos. |
| Programación | Cron externo que invoque endpoint interno autenticado del backend | Mantiene el proceso en el entorno desplegado gratuito sin depender de un worker siempre activo. Verificar límites del proveedor elegido. |
| Despliegue | Frontend en Vercel; API y PostgreSQL en servicios con plan gratuito que soporte la configuración; Supabase para DB/Storage es una alternativa compacta | Confirmar límites, suspensión, disponibilidad y cron antes de fijar proveedor. |
| Calidad | Pytest para reglas y API; pruebas de UI/manuales para flujo principal | El negocio tiene condiciones y transiciones críticas que conviene cubrir desde el inicio. |

La selección de proveedores no está fijada por el PDF: puede ajustarse si el entorno disponible impone otras opciones. La clave del correo, DB, bucket y cron se configura mediante secretos del despliegue, nunca en el repositorio.

## 3. Modelo de dominio y datos

Usar UUID como identificador, `timestamptz` en UTC para auditoría, `numeric`/`Decimal` para importes (nunca `float`) y restricciones/índices en base de datos además de validación de aplicación. Las fechas visibles se presentan en la zona configurada del usuario; la lógica de vencimiento utiliza instantes inequívocos.

### Entidades

- **users**: `id`, `name`, `email` único, `password_hash`, `role` (`admin|user`), `is_active`, `created_at`, `created_by`, `updated_at`, `updated_by`.
- **clients**: `id`, `name`, datos de contacto, `company_email` obligatorio para enviar, campos de contacto opcionales, auditoría.
- **products**: `id`, `name`, `description`, `default_unit_price`, `is_active`, auditoría. El precio en producto es referencia; la licitación conserva el precio acordado en la partida.
- **tenders**: `id`, `client_id`, `title`/`reference`, `description`, `status`, `budget_max`, `deadline_at`, `proposal_file_id` (nullable), `invoiced_total` (nullable hasta facturar), `reminder_sent_at` (nullable), `submitted_at`, auditoría.
- **tender_items**: `id`, `tender_id`, `product_id`, `quantity`, `unit_price`. Restricción `quantity > 0`, `unit_price >= 0`; único por licitación/producto salvo decisión de permitir líneas repetidas. Subtotal = cantidad × precio; total = suma de partidas.
- **proposal_files**: `id`, `tender_id`, proveedor/bucket, object key, nombre original saneado, MIME, tamaño, checksum opcional, `uploaded_by`, `uploaded_at`. La referencia de storage no debe ser una URL firmada que expire; se genera URL firmada al descargar.
- **payments**: `id`, `tender_id`, `amount`, `paid_at`, `reference`, `notes`, `created_by`, `created_at`. Restricción importe positivo.
- **tender_status_history**: `id`, `tender_id`, `from_status` (nullable al crear borrador), `to_status`, `actor_user_id` (nullable solo si actor del sistema), `reason`, `created_at`, `source` (`user|system`). Inmutable para usuarios normales.
- **email_outbox** (recomendado): evento/correo a enviar, destinatario, estado (`pending|sent|failed`), contador y próximo intento, proveedor ID, error resumido sin secretos, timestamps. Permite recuperación segura si el proveedor falla.
- **audit fields** en entidades mutables: creador/fecha y modificador/fecha según solicita el PDF.

### Invariantes

1. `tenders.status` se limita a `draft|active|finished|to_collect|collected|lost`; definir y documentar el mapeo con los nombres españoles del producto (`borrador`, `activa`, etc.).
2. `SUM(tender_items.quantity * unit_price) <= budget_max` después de cada alta/cambio de partida. Validar con transacción para evitar carreras concurrentes.
3. Partidas solo editables en `draft` o `active`? **El PDF prohíbe cambios desde `finalizada`, `por_cobrar`, `cobrada` y `perdida`; por tanto, interpreta que borrador y activa sí son editables.** La decisión de permitir edición cuando ya está activa es sensible y debe confirmarse. Recomendación de seguridad comercial: permitir cambios solo en borrador, salvo autorización explícita.
4. `draft → active` requiere propuesta cargada y envío de email confirmado/aceptado por proveedor, con operación idempotente para no duplicar envíos.
5. `active → finished|lost`; `finished → to_collect`; `to_collect → collected` al saldo cero. No admitir otras transiciones. Vencimiento solo afecta `active` y pasa a `lost`.
6. Pagos solo en `to_collect`, importe > 0 y menor/igual al saldo; insertar pago y transición a `collected` en una sola transacción cuando saldo = 0.
7. El saldo es `invoiced_total - SUM(payments.amount)`; no aceptar saldo negativo. La factura debe tener monto positivo y no inferior a pagos registrados (normalmente no hay pagos antes de facturar).
8. Toda transición de estado y su evento de correo deben ser recuperables/idempotentes. Evitar mantener una transacción SQL abierta mientras se llama al proveedor externo: usar outbox o un patrón equivalente.

## 4. Estados y reglas del flujo

```text
borrador --(propuesta adjunta + envío aceptado)--> activa
activa --(entrega ganada/completada)-------------> finalizada
activa --(resolución manual o vencimiento)--------> perdida
finalizada --(factura registrada)----------------> por_cobrar
por_cobrar --(saldo llega a cero)-----------------> cobrada
```

Cada comando debe usar el servicio de dominio de transición, comprobar el estado actual, aplicar restricciones y crear historial en la misma transacción. Rechazar transiciones inválidas con HTTP 409 y un código estable (por ejemplo `INVALID_STATUS_TRANSITION`). Errores de validación de datos: HTTP 422; no autenticado: 401; no autorizado: 403; recurso ausente: 404.

### Envío oficial y fallos externos

El email tiene un efecto externo imposible de incluir en una transacción SQL. Usar una operación idempotente: crear solicitud de envío/outbox con clave idempotente, validar documento y datos, enviar correo; activar y registrar historial solo cuando el proveedor acepte la solicitud, o persistir estado `sending` recuperable y completar con worker. Definir comportamiento si hay timeout ambiguo para no enviar duplicado. Evidencia de aceptación del proveedor no equivale a prueba de entrega en buzón; conseguir y conservar confirmación/captura para el entregable.

## 5. API mínima propuesta

Prefijo `/api/v1`; esquemas request/response y errores consistentes; Swagger/OpenAPI publicado en entorno de desarrollo y protegido/configurable en producción.

| Método y ruta | Uso / regla clave |
|---|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Sesión y usuario actual. |
| `GET /users`, `POST /users` | Crear/listar; creación exclusiva de admin. No devolver hashes. |
| `GET /clients`, `POST /clients` | Listar/crear clientes; validar correo de empresa. |
| `GET /products`, `POST /products` | Listar/crear productos. |
| `GET /tenders`, `POST /tenders` | Listado paginado con filtros; crear en borrador. |
| `GET /tenders/{id}` | Detalle con cliente, partidas, totales, documento, pagos, saldo e historial. |
| `POST /tenders/{id}/items`, `DELETE /tenders/{id}/items/{item_id}` | Editar partidas donde se permita; bloquear estados terminales y hacer cumplir presupuesto. |
| `POST /tenders/{id}/proposal` | Carga multipart; guardar en storage y persistir metadata tras validar el objeto. |
| `POST /tenders/{id}/send` | Validar borrador/documento/destinatario; correo oficial; transición a activa + historial. |
| `POST /tenders/{id}/transitions/finish`, `/lose` | Acciones manuales permitidas desde activa; registrar actor y razón. |
| `POST /tenders/{id}/invoice` | Registrar importe facturado y transición `finalizada → por_cobrar`. |
| `POST /tenders/{id}/payments` | Registrar abono, evitar sobrepago, saldo y transición automática al saldar. |
| `GET /tenders/{id}/history` | Historial cronológico inmutable. |
| `GET /dashboard/upcoming` | Extra opcional: activas próximas a vencer, ordenadas por fecha. |
| `POST /internal/jobs/tenders` | Endpoint de cron protegido por secreto, ejecución idempotente de vencimientos y recordatorios. |

El recurso `invoice` no está detallado como entidad en el PDF: se registra al menos monto/fecha dentro de la licitación (`tenders.invoiced_total`) para calcular saldo; confirmada la NO necesidad de módulo de facturas separado (decisión §11.3, 2026-10-07).

## 6. Procesos programados

Implementar una tarea periódica desplegada, por ejemplo cada hora (la frecuencia final depende del proveedor cron), con dos consultas independientes:

1. **Vencimiento:** `status=active AND deadline_at <= now()` → transicionar a `lost`, registrar historial como actor `system`, enviar opcionalmente aviso interno (no exigido).
2. **Recordatorio:** `status=active AND deadline_at > now() AND deadline_at <= now()+48h AND reminder_sent_at IS NULL` → encolar/enviar email de recordatorio y marcar envío solo cuando el proveedor confirme aceptación.

Agregar bloqueo/idempotencia por licitación (actualización condicional, transacción o lock) para que invocaciones concurrentes no dupliquen transición ni recordatorio. Registrar métricas/logs por corrida y permitir reintentos de emails fallidos sin repetir acciones completadas. El orden debe excluir licitaciones cuyo plazo ya expiró del recordatorio.

## 7. Seguridad, privacidad y operación

- Hash fuerte de contraseña, limitación de intentos de login, validación server-side y autorización por rol en backend (no basta ocultar botones en UI).
- Cookies seguras en producción; CORS restringido; defensa CSRF si cookie autenticada; evitar secretos o datos sensibles en logs.
- Validar tipo/tamaño de archivo y analizar riesgo de contenido; nombres aleatorios de objeto. Descargar propuestas vía URL firmada de corta duración con autorización.
- No exponer endpoint cron sin autenticación secreta rotatable y comparación segura; no registrar el secreto.
- Evitar inyección SQL mediante ORM/consultas parametrizadas; validar paginación y filtros.
- Auditoría de acciones: actor, fecha, entidad y cambios relevantes. No registrar contraseñas, tokens, URLs firmadas o contenido de propuesta.
- Copia/retención de datos conforme al servicio seleccionado; política de borrado y acceso a documentos por decidir.
- Correo: plantilla sobria y resumen con cliente, referencia, presupuesto, partidas, fecha límite y propuesta adjunta. Manejar límite de tamaño del proveedor.

## 8. Plan de ejecución de 10 días

La secuencia apunta al plazo del reto, no constituye garantía de disponibilidad de terceros. Mantener cada día una versión ejecutable y reservar días finales para deploy/evidencias.

| Día | Resultado demostrable | Trabajo |
|---|---|---|
| 1 | Proyecto arranca localmente y arquitectura acordada | Revisar criterios, elegir proveedores y límites gratuitos, crear repositorio público, estructura frontend/backend, Docker Compose de PostgreSQL, configuración `.env.example`, migraciones iniciales y README de arranque. |
| 2 | Login y roles funcionales | Modelo de usuarios, hash de contraseñas, login/logout/me, primer admin por seed controlado, middleware de autorización, alta/listado de usuarios solo admin. |
| 3 | Datos maestros | Clientes/productos y formularios/listados básicos; auditoría; validación de correo y precios. |
| 4 | Borradores y partidas | Crear/listar/detallar licitación; añadir/quitar partidas; cálculo decimal total/presupuesto en transacción; pruebas de reglas centrales. |
| 5 | Propuestas y almacenamiento real | Configurar storage, carga, metadata y descarga firmada; comprobar URL y rechazo de formatos/tamaños no permitidos. |
| 6 | Activación y email real | Integrar proveedor, plantilla de envío, adjunto real, transacción/outbox/idempotencia, validar transición borrador→activa e historial; realizar envío controlado a destinatario autorizado de prueba. |
| 7 | Resolución, factura y cobros | Acciones finalizar/perder, registro de factura, pagos parciales, impedir exceso, saldo y transición automática a cobrada; UI de seguimiento. |
| 8 | Cron y panel | Endpoint protegido + cron desplegado; vencimiento y recordatorios; idempotencia, logs; panel de próximas a vencer si el núcleo está estable. |
| 9 | Despliegue y recorrido integral | Desplegar API/UI/DB, aplicar migraciones, secretos, dominio/URLs, configurar cron, ejecutar flujo real de borrador a cobro con datos controlados. |
| 10 | Evidencias y entrega | Corregir defectos, README completo, documentar límites y configuración, recopilar captura/log del correo aceptado/recibido y URL real del documento, validar enlace público y entregar. |

**Regla de recorte si hay retraso:** priorizar integridad de reglas, persistencia, email, storage, cron desplegado y flujo público; posponer estética avanzada, panel extra, filtros complejos y extras. Nunca afirmar que una integración/deploy funciona sin evidencia observable del entorno desplegado.

## 9. Criterios de aceptación y evidencia

### Flujo funcional de aceptación

1. Admin inicia sesión y crea usuario; usuario normal no puede crear usuarios.
2. Se crean cliente con correo y productos.
3. Usuario crea borrador, añade productos y se rechaza una partida que excede presupuesto.
4. Se sube propuesta; el objeto es accesible vía URL firmada válida.
5. Enviar sin propuesta se rechaza; con propuesta se envía correo real con adjunto, y queda activa con historial.
6. No se permiten transiciones fuera de la matriz. Cambios prohibidos de partidas en estados bloqueados se rechazan.
7. Tarea desplegada convierte activa vencida en perdida una vez; activa dentro de 48h recibe un único recordatorio.
8. Activa puede resolverse como finalizada o perdida; finalizada puede facturarse; pagos válidos actualizan saldo; exceso se rechaza; saldo cero produce cobrada.
9. Detalle presenta datos, historial, partidas y cobros auditables.
10. URL desplegada, README reproducible y dos evidencias adjuntas: recepción/envío del email con archivo y acceso del archivo almacenado.

### Evidencias a guardar en el repositorio (sin secretos ni datos personales reales)

- Capturas del flujo UI con datos ficticios.
- ID/registro del proveedor que pruebe el envío del correo; captura de buzón de prueba si el reto exige recibido.
- URL pública o temporal del archivo con fecha de verificación (ocultar tokens de URL firmada antes de publicar evidencia); idealmente demostrarla en navegador sin publicar una credencial duradera.
- Enlace al despliegue y hash/commit de la versión evaluada.
- Registro de ejecución del cron y resultado de vencimiento/recordatorio, redactado para no exponer secretos.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación / señal temprana |
|---|---|
| Plan gratuito suspende API/DB o limita cron | Verificar cuotas y comportamiento el día 1; elegir proveedor alternativo antes de construir despliegue específico. |
| Envío de email inconsistente con cambio de estado | Outbox, idempotencia y recuperación de estado; probar timeout/reintento. |
| Adjunto excede límite de email | Validar tamaño antes de enviar; documentar límite y mensaje de error. |
| URL de archivo queda pública | Bucket privado + URL firmada temporal; evidenciar acceso real sin dejar documento comercial abierto. |
| Carrera al modificar partidas o registrar pagos | Transacciones, constraints/locks y pruebas concurrentes donde aplique. |
| Cron duplica o pierde recordatorios | Ejecución idempotente y `reminder_sent_at`/registro de evento con estados/reintentos. |
| Diferencias zona horaria en vencimientos | Guardar UTC, definir semántica de `fecha_límite` (fecha vs instante), testear frontera del deadline. |
| PDF no define monto/entidad de factura ni edición en activa | Registrar decisiones antes de codificar y explicarlas en README; consultar al solicitante si puede aclararse. |
| Se confunde prueba local con aceptación final | Separar evidencia local de evidencia de producción; checklist del entorno desplegado al día 9-10. |

## 11. Decisiones pendientes para iniciar

1. ~~¿Permitir editar productos y precios cuando la licitación está `activa`?~~
   **RESUELTA (2026-10-07):** las partidas solo se editan en `draft`. Se
   adopta la recomendación de seguridad comercial del plan §3; `active` y los
   estados terminales rechazan cambios de partidas (409
   `INVALID_STATUS_TRANSITION`).
2. ~~Storage de propuestas antes de tener credenciales de Supabase.~~
   **RESUELTA (2026-10-07, día 5-6):** se implementa `app/services/storage.py`
   con interfaz única y adaptador `local` para desarrollo (disco local,
   gitignored, nombres aleatorios y misma semántica de objeto/bucket/key).
   Cuando existan `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`, se añade el
   adaptador `supabase` (URL firmada real) sin tocar la lógica de negocio.
   La URL firmada verificable queda pendiente hasta configurar Supabase.

3. ~~¿El monto facturado siempre es igual al total de partidas, o se permite
   registrar un monto distinto? ¿Se necesita entidad de factura y número
   fiscal?~~
   **RESUELTA (2026-10-07, día 7):** se permite registrar un importe
   facturado DISTINTO del total de partidas (negociación/descuentos
   comerciales), siempre estrictamente positivo y no inferior a la suma de
   pagos ya registrados (422 `INVOICE_BELOW_PAYMENTS`). Sin entidad de
   factura separada ni número fiscal: el PDF no lo exige y el plan §5 lo
   dejaba a confirmar; `tenders.invoiced_total` guarda el monto y los
   pagos registran su propia referencia/fecha. Si el solicitante pidiera
   facturación fiscal completa, se añadiría una entidad `invoices` al
   mismo flujo.
4. ~~¿La fecha límite representa una fecha local hasta fin del día o un
   instante exacto con hora?~~
   **RESUELTA (2026-10-07, día 8):** `deadline_at` es un INSTANTE EXACTO en
   UTC (`timestamptz`). La licitación vence en el momento en que
   `deadline_at <= now()`; el recordatorio se dispara cuando
   `now() < deadline_at <= now() + 48h`. La UI puede presentar la fecha en
   la zona del usuario, pero la lógica de vencimiento usa instantes
   inequívocos, como ya modela el esquema.
5. ¿Propuestas deben ser siempre privadas con enlace firmado, y cuál es el máximo de tamaño/formato aceptable?
6. ¿Qué proveedor gratuito y cuenta están disponibles para despliegue, email, storage y cron? Verificar límites actuales antes de comprometer arquitectura final.
7. ¿Qué información de contacto del cliente es obligatoria aparte de correo de empresa?
8. ~~¿Se pueden editar o borrar clientes?~~ **RESUELTA (2026-10-08):** se añade
   `PATCH /clients/{id}` (edición parcial; unicidad de correo con 409) y
   `DELETE /clients/{id}` con **borrado lógico** (`clients.deleted_at`): la
   fila permanece en BD (licitaciones, historial y auditoría intactos), deja
   de aparecer en el listado y en la web, y no admite nuevas licitaciones
   (404 `CLIENT_NOT_FOUND`). Impacto: modelo + migración Alembic + API +
   frontend (botones Editar/Eliminar) + pruebas (10 casos nuevos). La
   unicidad del correo sigue aplicando a TODAS las filas, borradas incluidas.
9. ~~CSRF con cookies autenticadas.~~ **RESUELTA (2026-10-08):** la cookie JWT
   viaja con `SameSite=lax` (bloquea envíos cross-site de métodos sensibles)
   y el frontend es mismo-origen (`/api/*` → rewrite de Next; sin CORS
   abierto; `credentials: same-origin`). Los endpoints mutan solo por
   POST/PATCH/DELETE con `Content-Type: application/json`, que un formulario
   cross-site no puede emitir sin CORS. No se añade token CSRF: el
   mismo-origen + SameSite=lax + JSON cubren el riesgo para esta prueba.
   Complemento anti fuerza bruta: limitador por IP en `/auth/login`
   (`login_max_attempts`/`login_window_seconds`, en memoria, en
   `app/core/ratelimit.py`). El listado `GET /users` pasó a requerir admin
   (403 para rol user; el menú lo oculta al resto).
10. **Despliegue — DECISIÓN TOMADA (2026-10-08): un solo origen en RENDER
    + Supabase + cron externo.** El PDF de origen describe VPS propio con
    Docker Compose, pero la selección de proveedores no está fijada por el
    PDF (ítem 6 de esta lista; la tabla "Despliegue" cita Render
    explícitamente; riesgo "Plan gratuito suspende…") y se prefiere una
    alternativa gestionada al VPS propio; se elige Render.
    Elección final:
    - **App completa (API + frontend) en Render (plan free) como UN web
      service de un solo origen**: uvicorn :8000 + Next.js standalone :3000
      en el mismo contenedor (`Dockerfile` de la raíz), detrás de un único
      dominio https `*.onrender.com`. Se conserva la cookie JWT
      `SameSite=lax` misma-origen y el rewrite local `/api/*`; el cron
      entra por `POST /internal/jobs/tenders` vía rewrite `/internal/*`
      (añadido al frontend el 2026-10-08). `ENVIRONMENT=production` y
      `COOKIE_SECURE=true` por variable de entorno. Free tier: el servicio
      duerme tras ~15 min sin tráfico (cold start 30-60 s; el ping del
      cron externo lo despierta; aceptable para la prueba).
    - **Postgres y Storage en Supabase** (proyecto ya contratado):
      migraciones Alembic contra el Postgres gestionado al primer arranque
      (entrypoint idempotente) + seed del admin. Motivo extra frente a
      Postgres free de Render: Render lo borra a los 30 días; Supabase no
      expira.
    - **Cron externo**: cron-job.org primero (no depende de GitHub);
      GitHub Actions `schedule:` queda disponible al subir el repo.
    - **Dependencia estructural**: Render despliega desde un repo git
      (GitHub) o desde una imagen pública (Docker Hub). Pendiente de
      decidir: empujar el repo a GitHub ya, o desplegar por imagen sin Git.
    Impacto (este mismo trabajo): `Dockerfile` (multi-etapa, raíz) +
    `render.yaml` + `deploy/entrypoint.sh` + `.dockerignore`; rewrites
    `/internal/*`, `/docs`, `/openapi.json` en el frontend; runbook en
    `docs/DEPLOY.md`. **ESTADO: DESPLEGADO el 2026-10-08** en
    https://csc-licitaciones.onrender.com (commit `c354c00`); pendiente:
    cron externo ejecutándose y evidencias del recorrido UI en este
    entorno (docs/evidencias/dia10_desplegado.md).

## 12. Convenciones para mantener contexto

- Este archivo define intención, decisiones y criterios; actualizarlo cuando una decisión cambie, anotando fecha, motivo e impacto.
- Mantener `README.md` para instalación/uso/despliegue y este plan para alcance/modelo/reglas/roadmap.
- Cada cambio de regla debe actualizar modelo, API, pruebas y este documento en el mismo trabajo.
- Al reportar avances, indicar explícitamente qué está implementado, qué está probado localmente, qué está probado en despliegue y qué evidencia concreta existe.
- No marcar como completado email, storage, cron o deploy solo porque el código compila o exista configuración; comprobar resultado real y guardar evidencia.

## Referencia de requisitos

Requisitos extraídos de las secciones del PDF: contexto del negocio; relaciones; acceso y seguridad; estados y transiciones; reglas 1–7; API mínimo; requisitos técnicos; entregables; extras y criterios de evaluación. Ante conflicto, revisar el PDF original y dejar registrado cualquier interpretación adoptada.


Decisiones Tecnológicas - Sistema de Gestión de Licitaciones

Este documento recopila las decisiones de arquitectura y servicios externos definidos para el desarrollo de la prueba técnica del Sistema de Gestión de Licitaciones.

1. Stack Tecnológico Principal

Backend: Python con FastAPI

Frontend: Next.js (conectado al API de FastAPI)

Base de Datos: PostgreSQL corriendo en contenedores Docker (alojado en VPS propio)

ORM: SQLModel

Migraciones de Base de Datos: Alembic (para el versionado y control de cambios en el esquema de PostgreSQL).

2. Seguridad y Autenticación

Autenticación: Basada en JWT / Cookies seguras (HttpOnly, Secure en producción) con roles base (admin / user).

Hash de Contraseñas: Argon2id (o Bcrypt mediante Passlib) para el almacenamiento seguro de credenciales.

Control de Acceso: Restricción estricta donde solo los usuarios con rol admin pueden registrar nuevos usuarios en el sistema. Auditoría completa de creación/modificación en entidades y registro en historial para cada transición de estado.

3. Integraciones Obligatorias y Almacenamiento

Proveedor de Email Transaccional: Resend (con soporte real de envíos y adjuntos).

Fiabilidad: Implementación de un patrón de persistencia tipo Outbox o manejo de idempotencia para asegurar que los correos y las activaciones de estado no se dupliquen ante fallos de red.

Almacenamiento de Archivos: Supabase Storage (para alojar los documentos de propuesta).

Privacidad: Los archivos no serán de acceso público permanente; se generarán URLs firmadas (Signed URLs) de corta duración bajo autorización para su descarga segura.

4. Automatización y Tareas Programadas (Jobs)

Mecanismo: Script en Python para revisar el vencimiento de licitaciones y enviar recordatorios, ejecutado mediante un Cron nativo en el VPS (sistema operativo Linux) que invoque un endpoint protegido del backend con una clave secreta.

5. Pruebas y Calidad (Testing)

Testing Backend: Pytest para la validación automatizada de la API, las reglas de negocio críticas, los cálculos de presupuesto y la matriz estricta de transiciones de estado.

6. Despliegue e Infraestructura

Backend, Base de Datos y Cron: Desplegado en VPS propio utilizando Docker y Docker Compose.

Frontend: Desplegado en Vercel o en el mismo VPS apuntando al API de FastAPI.
