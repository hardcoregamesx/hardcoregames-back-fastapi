# Endpoints de cuotas y reserva (fase 1)

Fuente de verdad completa: `hardcoregames-back/docs/cuotas-y-reserva.md`. Este
documento cubre solo lo que expone **este repo** (FastAPI): los campos nuevos
en productos/combinaciones/carrito y el router `/payment-plans/`. Django es
quien cobra y confirma los pagos (checkout, webhooks, pago de cuotas
siguientes) -- ver §4 de la spec completa.

## Campos nuevos en productos (tarjetas)

Añadidos, de forma aditiva, a `GET /products/`, `/products/pagination`,
`/products/favorites`, `/products/week-offers`, `/products/filter`,
`/products/by-date`, `/products/search`, `/products/most-sold`,
`/products/recommended` y al detalle `GET /products/{id_product}`:

| Campo | Tipo | Significado |
|---|---|---|
| `fecha_lanzamiento` | `string` (ISO `YYYY-MM-DD`) o `null` | Del `Product`. `null` para el catálogo normal. |
| `cuotas_desde` | `int` o `null` | Mínimo `valor_cuota` entre variantes del producto con `cuotas_activas=true` y `stock>0`. `null` si ninguna variante tiene cuotas. |
| `cuotas_num` | `int` o `null` | `num_cuotas` de la variante que fija `cuotas_desde` (misma fila). |
| `reserva_monto` | `int` o `null` | Mínimo `monto_reserva` entre variantes con `reserva_activa=true`, solo si `fecha_lanzamiento` es futura. `null` en cualquier otro caso. |

`cuotas_desde`/`cuotas_num`/`reserva_monto` se calculan con dos consultas
agrupadas por producto (`GameDetail.producto_id`), nunca una consulta por
producto — ver `_get_plan_aggregates_for_products` en
`app/routers/products.py`. El detalle (`/products/{id_product}`) solo agrega
`fecha_lanzamiento`, no los tres agregados (la página de producto ya pide el
detalle real de cada variante a `combination-price`).

Ejemplo (`GET /products/filter?...`):

```json
{
  "data": [
    {
      "id_product": 42,
      "title": "God of War Ragnarök",
      "price": 180000,
      "price_discount": 150000,
      "fecha_lanzamiento": null,
      "cuotas_desde": 60000,
      "cuotas_num": 3,
      "reserva_monto": null,
      "consoles": [{"id_console": 1}]
    },
    {
      "id_product": 99,
      "title": "GTA VI",
      "price": 350000,
      "price_discount": 0,
      "fecha_lanzamiento": "2026-11-19",
      "cuotas_desde": null,
      "cuotas_num": null,
      "reserva_monto": 20000,
      "consoles": [{"id_console": 1}, {"id_console": 2}]
    }
  ]
}
```

## Campos nuevos en combinaciones — `GET /products/combination-price/{id_product}`

Cada grupo de `data[]` agrega los seis campos crudos de la variante (todas
las filas físicas de la misma combinación comparten estos valores, así que se
toman de la primera fila del grupo):

| Campo | Tipo |
|---|---|
| `cuotas_activas` | `bool` |
| `num_cuotas` | `int` |
| `valor_cuota` | `int` |
| `cuota_inicial` | `int` o `null` |
| `reserva_activa` | `bool` |
| `monto_reserva` | `int` |

Ejemplo:

```json
{
  "message": "proceso exitoso",
  "product_id": 42,
  "data": [
    {
      "pk": 501,
      "consola": 1,
      "desc_console": "PS5",
      "licencia": 1,
      "desc_licence": "Primaria",
      "stock": 4,
      "precio": 180000,
      "precio_descuento": 150000,
      "duracion_dias_alquiler": null,
      "cuotas_activas": true,
      "num_cuotas": 3,
      "valor_cuota": 60000,
      "cuota_inicial": null,
      "reserva_activa": false,
      "monto_reserva": 20000
    }
  ],
  "code": "00",
  "status": 200
}
```

## Carrito — `app/routers/shopping_car.py`

### `POST /shopping-car/`

- Body nuevo: `modo_pago` (opcional, default `"contado"`; valores válidos
  `"contado" | "cuotas" | "reserva"`). **Un cliente viejo que no manda este
  campo sigue funcionando exactamente igual que antes.**
- 400 si `modo_pago` no es uno de los tres valores válidos.
- 400 si `modo_pago="cuotas"` y la variante no tiene `cuotas_activas`, o
  `modo_pago="reserva"` y no tiene `reserva_activa`.
- 409 sin cambios: la variante ya en el carrito del usuario (con cualquier
  modo) rechaza el alta — "una misma variante no puede estar dos veces con
  modos distintos" (spec §1) queda cubierto por la regla de duplicado que ya
  existía.

### `GET /shopping-car/`, `GET /shopping-car/{id}`, `PUT /shopping-car/{product_id}`

Cada ítem del carrito ahora incluye, de forma aditiva:

| Campo | Tipo | Significado |
|---|---|---|
| `modo_pago` | `string` | `"contado"` para filas viejas (default de columna). |
| `pago_hoy` | `int` o `null` | Lo que se cobraría hoy por este ítem: contado → precio de contado; cuotas → `cuota_inicial` (o `valor_cuota` si no hay inicial fija); reserva → `monto_reserva`. |
| `cuotas_activas`, `num_cuotas`, `valor_cuota`, `cuota_inicial`, `reserva_activa`, `monto_reserva` | — | Los seis campos de plan de la variante, iguales a `combination-price`. |

Ejemplo (`GET /shopping-car/`):

```json
[
  {
    "id_shopping_car": 10,
    "user_id": 5,
    "product_id": 501,
    "estado": true,
    "product_price": 150000,
    "title": "God of War Ragnarök",
    "image": "https://...",
    "desc_console": "PS5",
    "desc_licence": "Primaria",
    "consola": 1,
    "licencia": 1,
    "duracion_dias_alquiler": null,
    "modo_pago": "cuotas",
    "pago_hoy": 60000,
    "cuotas_activas": true,
    "num_cuotas": 3,
    "valor_cuota": 60000,
    "cuota_inicial": null,
    "reserva_activa": false,
    "monto_reserva": 20000
  }
]
```

## `POST /auth/set-password`

- Auth: JWT Bearer (`get_current_user`).
- Body: `{"new_password": "...", "confirm_password": "..."}` (mínimo 8
  caracteres cada una).
- Solo funciona si el perfil (`UserCustomized`) tiene `is_guest_account=true`;
  si no, **400** "Esta cuenta ya tiene contraseña propia." (evita que sirva
  como un "cambiar contraseña" genérico — para eso ya existe
  `/auth/reset-password` con el flujo de correo).
- 400 si `new_password != confirm_password`.
- Hashea con el mismo `get_password_hash` (pbkdf2_sha256, compatible con
  Django) que usa `/auth/register` y `/auth/reset-password`.
- Al confirmar, pone `is_guest_account=false`.

Respuesta:

```json
{"message": "Contraseña creada correctamente"}
```

## Router `/payment-plans/`

Nuevo archivo `app/routers/payment_plans.py`, registrado en `app/main.py`.
Solo lectura: Django escribe los planes y sus cuotas (checkout, webhooks,
pago de cuotas siguientes — spec §4); este router arma el shape que consume
el frontend, con dos consultas agrupadas por tanda de planes (nunca una
consulta por plan), incluso en `GET /payment-plans/`.

Shape común de un plan (`PlanRead`):

```json
{
  "id": 12,
  "tipo": "cuotas",
  "estado": "activo",
  "titulo_snapshot": "God of War Ragnarök | Primaria | PS5",
  "producto_titulo": "God of War Ragnarök",
  "producto_imagen": "https://.../gow.jpg",
  "precio_total": 180000,
  "descuento": 0,
  "total_pagado": 60000,
  "mora_acumulada": 0,
  "retirado": false,
  "token": "AbCdEf123...",
  "fecha_creacion": "2026-09-17T14:30:00Z",
  "fecha_lanzamiento": null,
  "cuotas": [
    {"id": 30, "numero": 1, "monto": 60000, "mora": 0, "fecha_vencimiento": null, "estado": "pagada", "fecha_pago": "2026-09-17T14:30:00Z"},
    {"id": 31, "numero": 2, "monto": 60000, "mora": 0, "fecha_vencimiento": "2026-10-17", "estado": "pendiente", "fecha_pago": null},
    {"id": 32, "numero": 3, "monto": 60000, "mora": 0, "fecha_vencimiento": "2026-11-16", "estado": "pendiente", "fecha_pago": null}
  ],
  "proxima_cuota": {"id": 31, "numero": 2, "monto": 60000, "mora": 0, "fecha_vencimiento": "2026-10-17", "estado": "pendiente", "fecha_pago": null},
  "puede_pagar": true
}
```

Nota de nombres: `producto_titulo`/`producto_imagen` son el título/imagen
**vivos** del producto (pueden diferir de `titulo_snapshot` si el producto se
renombró después de crear el plan). Se nombran distinto a propósito para no
confundirlos con el snapshot congelado — decisión de esta implementación, la
spec solo decía "imagen y título del producto".

### `GET /payment-plans/`

- Auth: JWT Bearer.
- Devuelve la lista de planes del usuario autenticado, ordenados por próximo
  vencimiento (los que tienen una cuota pendiente con fecha, de más cercana a
  más lejana; el resto — reservas esperando stock, planes completados,
  cancelados o retirados — al final).
- Respuesta: `PlanRead[]` (shape de arriba).

### `GET /payment-plans/by-token/{token}`

- Sin autenticación (pensado para el enlace de correo
  `https://www.hardcoregames.co/pagos/<token>`, incluye invitados).
- 404 si el token no existe.
- Respuesta: `PlanRead` + `user_email` (enmascarado, `"ju***@gmail.com"`) +
  `is_guest_account`.

```json
{
  "...": "... mismos campos que PlanRead ...",
  "user_email": "ju***@gmail.com",
  "is_guest_account": true
}
```

### `GET /payment-plans/pending-count`

- Auth: JWT Bearer.
- Cuenta cuotas `pendiente` con `fecha_vencimiento` no nula, vencidas o que
  vencen en los próximos 7 días, de planes que no están `completado`,
  `cancelado` ni `retirado`.
- Alimenta el badge del botón dorado "Pagos pendientes".

```json
{"count": 2}
```

## Decisiones y desviaciones respecto a la spec

- **Nombres de los campos vivos de producto en `PlanRead`**: la spec dice
  "imagen y título del producto" sin nombrar los campos. Se usó
  `producto_titulo`/`producto_imagen` (en vez de, por ejemplo, `titulo`/
  `imagen` a secas) para que no se confundan con `titulo_snapshot`.
- **`puede_pagar`**: implementado como "hay al menos una cuota `pendiente`
  con `fecha_vencimiento` no nula, o el plan es una reserva en estado
  `asignado`". La fase 1 no incluye la asignación de cuentas de una reserva
  (eso es fase 3), así que en la práctica una reserva recién creada siempre
  tiene `puede_pagar=false` hasta que exista esa función.
- **`proxima_cuota`**: solo considera cuotas pendientes con fecha. El saldo
  de una reserva (cuota #2, `fecha_vencimiento=NULL` hasta que se asigne
  cuenta) nunca aparece como "próxima cuota" — no hay fecha que mostrar
  todavía.
- **Validación de `modo_pago` en `POST /shopping-car/`**: la spec solo pide
  aceptar el campo y rechazar 409 por duplicado; se añadió además una
  validación 400 si la variante no tiene `cuotas_activas`/`reserva_activa`
  para el modo pedido. Es una validación defensiva adicional (Django sigue
  siendo la fuente de verdad dura en el checkout, `_calculate_cart_amount`),
  pero evita carritos con datos inconsistentes antes de llegar ahí.
- No se tocó nada de §3 (SQL) más allá de espejar las columnas en
  `app/models.py`: el DDL real lo aplica Django (`products/sql/2026-09-
  cuotas-reserva.sql`), como pide la spec.
- No se implementó nada de fases 2-4 (recordatorios/mora automática,
  reservas admin, migración de productos "A CUOTAS").

## Qué no se pudo verificar

- No hay acceso a una base Postgres real con las columnas de §3 ya
  aplicadas en este entorno de desarrollo, así que las consultas nuevas
  (agregados de productos, `combination-price`, `/payment-plans/*`) se
  verificaron por lectura de código y por que el proyecto importa sin
  errores (`python -c "import app.main"`), no con una llamada HTTP real
  contra datos de producción.
- No se corrió el SQL de §3 aquí (le corresponde a Django, y el orden de
  despliegue de la spec —§8— pone el SQL antes que FastAPI).
