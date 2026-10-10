# Manual del usuario — CSC (Sistema de Gestión de Licitaciones)

Versión para usuarios finales. Si es tu primera vez entrando a la
plataforma, este documento te explica qué es, qué puedes hacer y cómo
funciona todo el ciclo, en lenguaje sencillo.

---

## 1. ¿Qué es CSC?

CSC es la plataforma web de tu equipo comercial para llevar el control
**completo del ciclo de vida de una licitación**: desde que surge la
oportunidad, se prepara la oferta, se envía al cliente de forma oficial,
se da seguimiento (¿ganamos o perdimos?), hasta que se factura y se cobra.

Todo queda registrado en un solo lugar: los clientes, los productos que
ofreces, el presupuesto de cada licitación, el documento de propuesta, la
fecha límite, los correos enviados y el historial de cada licitación.

Lo más importante: **la plataforma aplica sola todas las reglas del
negocio** y te avisa con correos en los momentos clave. No puedes "romper"
el proceso: si un paso no se puede hacer, el sistema te dice por qué.

## 2. Quién puede usarla

- **Usuarios estándar** — crean y gestionan clientes, productos y
  licitaciones, y recorren todo el ciclo (enviar, finalizar, perder,
  facturar, cobrar).
- **Administradores** — hacen todo lo anterior y además **crean y
  gestionan usuarios** (es la única diferencia; las cuentas solo las crea
  un administrador).

## 3. Cómo entrar

1. Abre la dirección de la plataforma (p. ej. `http://localhost:3000` en
   desarrollo, o la dirección oficial en producción).
2. Escribe tu correo corporativo y tu contraseña.
3. Listo: entras directo al panel de **Licitaciones**.

> Tu cuenta te la crea un administrador. Si aún no tienes una, pídesela.

## 4. Las cuatro secciones

En el menú superior verás:

| Sección | Para qué sirve |
|---|---|
| **Licitaciones** | El corazón del sistema: aquí ves todos los procesos, creas nuevos, los envías y los gestionas hasta el cobro. |
| **Clientes** | Tu cartera: nombre y correo corporativo de cada cliente. Puedes **editar** o **eliminar** cualquiera (el borrado es lógico: desaparece de las listas, pero sus licitaciones se conservan). |
| **Productos** | El catálogo de productos con su precio de referencia. |
| **Usuarios** | Solo visible para administradores: crear y ver las cuentas del equipo. |

## 5. El ciclo de vida de una licitación

Cada licitación pasa por etapas. La que estás viendo se muestra siempre
con una etiqueta en español:

```
Borrador → Activa → Finalizada  → Por cobrar → Cobrada
                      o Perdida ↗
```

| Etapa | Qué significa | Qué puedes hacer |
|---|---|---|
| **Borrador** | La estás preparando; nadie la vio todavía. | Agregar/quitar partidas, subir la propuesta, darle "Enviar oficialmente" cuando esté lista. |
| **Activa** | Ya se envió la propuesta al cliente (por correo, con el documento adjunto). | Esperar la respuesta. Puedes marcarla **Perdida** o, si ganan, **Finalizada**. |
| **Finalizada** | Ganada y entregada. | Registrar la **factura** (importe a cobrar). |
| **Por cobrar** | Se facturó; toca cobrar. | **Registrar pagos** (parciales o totales) y ver el saldo pendiente. |
| **Cobrada** | Se cobró todo. | Nada más: la licitación está cerrada. ✅ |
| **Perdida** | No ganamos (lo marcas tú o el sistema al vencer el plazo). | Nada más. |

En el **detalle** de cada licitación ves las partidas con su subtotal, el
total, el presupuesto máximo, los pagos con su historial y la línea de
tiempo con cada cambio de etapa ("Borrador → Activa").

## 6. Tu primer flujo típico (paso a paso)

1. **Clientes** → crea el cliente (nombre + correo corporativo).
2. **Productos** → crea los productos que vas a ofrecer.
3. **Licitaciones** → "Nueva licitación": cliente, título, referencia,
   presupuesto máximo y fecha límite. Se crea como **Borrador**.
4. Abre la licitación y **añade partidas**: producto, cantidad y precio
   unitario. El total se calcula solo.
5. Sube el **documento de propuesta** (PDF, Word, etc.; máx. 10 MB).
6. **Enviar oficialmente** → al cliente le llega un correo automático con
   el resumen (productos, presupuesto, fecha límite) y el documento.
7. Cuando haya respuesta: **Finalizar** (ganamos) o **Perder**.
8. Al finalizar, **Facturar**: indica el importe a cobrar.
9. **Registrar pago** (parcial o total). El saldo pendiente se actualiza
   solo.
10. Con el último pago, la licitación pasa a **Cobrada** automáticamente.
    Proceso cerrado.

## 7. Qué hace la plataforma SOLA (automático)

- **Correo al enviar**: cuando envías una propuesta, sale un correo real
  al cliente con el resumen y el adjunto.
- **Recordatorio**: si una licitación **Activa** está a menos de 48 horas
  del plazo y no se le ha recordado, envía UN único correo de
  recordatorio.
- **Pérdida por vencimiento**: si la fecha límite pasa y sigue **Activa**,
  el sistema la pasa a **Perdida** automáticamente (un trabajo programado,
  sin intervención humana).
- **Cobro automático**: al registrar el pago que deja el saldo pendiente
  en cero, la licitación queda **Cobrada** en el mismo instante.

## 8. Reglas que no puedes saltarte (y por qué)

- **Presupuesto**: el total de partidas no puede superar el presupuesto
  máximo de la licitación.
- **Propuesta obligatoria**: no se puede enviar una licitación sin tener
  el documento de propuesta subido.
- **Estados cerrados**: cuando una licitación está **Enviada, Finalizada,
  Por cobrar, Cobrada o Perdida**, ya no puedes agregar ni quitar
  productos. Primero decide bien el contenido del borrador.
- **Sin sobrepago**: no puedes registrar un pago mayor que el saldo
  pendiente, ni pagos en etapas que no sean **Por cobrar**.
- **Cambiar de etapa**: cada avance debe seguir el orden correcto; si la
  plataforma detecta un salto inválido, te lo rechaza con un aviso claro.

## 9. Preguntas frecuentes

- **¿Puedo quitar una partida después de enviar?** No. Revisa el contenido
  del borrador antes de enviar.
- **¿Y si el cliente paga de más?** No se puede: la plataforma rechaza los
  pagos que exceden el saldo.
- **¿Dónde se guardan los documentos?** En almacenamiento privado en la
  nube; solo se descargan a través de la plataforma con una URL temporal
  y segura. Nunca están expuestos públicamente.
- **¿Me equivoqué al crear un cliente?** Desde la lista de Clientes puedes
  **Editar** (corregir nombre, correo o contactos) o **Eliminar** el
  cliente. El borrado es lógico: deja de aparecer en las listas y en la
  web, pero sus licitaciones pasadas se conservan para consulta.
- **¿Quién puede crear usuarios?** Solo los administradores.
- **¿Qué hago si olvidé la contraseña?** Pide a un administrador que
  gestione tu cuenta.
- **¿La fecha límite se puede cambiar?** Se fija al crear la licitación;
  los cambios de plazo no están disponibles en la versión actual.

## 10. Consejo final

Usa la referencia de cada licitación para encontrarla rápido, revisa
siempre el resumen antes de enviar (ese correo es oficial y va con tu
documento adjunto) y registra los pagos apenas lleguen: así el saldo y
los estados están siempre al día y tu equipo ve la realidad comercial en
un vistazo.