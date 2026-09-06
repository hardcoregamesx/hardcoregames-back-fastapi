# Endpoints para el agente de chats

Dos endpoints pensados para que un agente de IA cotice por WhatsApp, Chatwoot o
Marketplace sin abrir el navegador ni conectarse a Postgres.

## Por que no sirve `/products/search`

`/products/search` esta hecho para la grilla de la web, no para cotizar:

| | `/products/search` | `/products/agent-search` |
|---|---|---|
| Precio | el **minimo** del producto | el que se cobra, por variante |
| Stock | no lo devuelve | si, sumado por oferta |
| Consola | solo `id_console` | nombre (`PS5`, `Xbox Series X`) |
| Payload | arrastra `description`, `image`, `calification`... | solo lo necesario |

El precio minimo es el problema serio: si un juego vale $120.000 en PS4 y
$180.000 en PS5, `/products/search` devuelve $120.000 para las dos. Un agente
que cotice con eso promete un precio que no existe.

## Configuracion

```bash
AGENT_API_KEY=<cadena larga y aleatoria>
```

Sin esta variable los endpoints responden **503** (fallan cerrados, no abiertos).

Generala en el servidor, nunca en un chat ni en un commit:

```bash
openssl rand -hex 32
```

### Dos formas de mandarla

```bash
# Preferida: por cabecera
curl -H "X-API-Key: $AGENT_API_KEY" "$HG_API/products/agent-search?q=FC%2027"

# Alternativa: por query param
curl "$HG_API/products/agent-search?q=FC%2027&key=$AGENT_API_KEY"
```

El query param existe para agentes que solo pueden **navegar a una URL** y no
pueden fijar cabeceras (por ejemplo un agente operando el navegador). Tiene un
coste: la clave queda en el historial del navegador y en los logs de acceso del
servidor. Solo expone precios y stock, no datos de clientes ni de pago, pero
conviene rotarla cada cierto tiempo. Usa la cabecera siempre que puedas.

## `GET /products/agent-search`

```bash
curl -s -H "X-API-Key: $AGENT_API_KEY" \
  "$HG_API/products/agent-search?q=FC%2027%20para%20PS5"
```

```json
{
  "q": "FC 26 para PS5",
  "termino": "fc26",
  "plataformas": ["playstation5"],
  "resultados": [
    {"producto": "EA FC 26 Standard", "consola": "PlayStation 5",
     "licencia": "Secundaria", "precio_final": 99990,
     "precio_lista": 169990, "stock": 7}
  ],
  "agotados_ocultos": 1
}
```

### El precio viene ya resuelto

`precio_final` es **lo que se cobra**, con la misma regla que el carrito
(`_effective_price` en `shopping_car.py`: el descuento manda si es mayor que 0 y
menor que la lista). `precio_lista` solo aparece cuando hay descuento real, para
poder decir "antes 169.990, ahora 99.990".

Se expone asi a proposito. Devolver `precio` y `precio_descuento` y dejar que el
agente elija es justo lo que hace que se cotice mal.

### Las filas se agrupan por oferta

`products_gamedetail` guarda una fila por cuenta o lote, asi que la misma
combinacion de producto, consola y licencia sale repetida. Se agrupan con la
misma clave que `/products/combination-price` y se **suma el stock**.

Sin esto el agente ve la oferta cuatro veces y anuncia un stock parcial: diria
"quedan 5" teniendo 7.

Parametros: `q` (requerido), `only_stock` (por defecto `true`), `limit` (25).

Notas de comportamiento:

- **La plataforma se extrae de la consulta y no contamina la busqueda.**
  `"FC 27 para PS5"` busca `fc27` y usa `PS5` para elegir la fila. Es el fallo
  que tiene `/products/search`, donde esa misma consulta devuelve cero filas.
- Si la plataforma no casa con ninguna fila, se devuelven **todas** en vez de un
  "no disponible" falso: es mejor ofrecer otra consola que negar el producto.
- La consola se compara **exacta** contra `products_consoles`, no por substring:
  `"xboxseries"` contiene `"xbox"`, y con substring quien pedia una Xbox One
  veia filas de Series.
- `products_consoles` tiene un `"xbox"` generico sin generacion (id 5). Vale
  para cualquier consulta de la familia Xbox: ocultar ese stock a quien pide
  una Series es peor que mostrarlo, porque la fila lleva el nombre y el cliente
  puede juzgar.
- Una ficha en `"Multiplataforma"` casa con cualquier plataforma que pida el
  cliente. Sin esa regla no casaria con ninguna.
- `agotados_ocultos` permite distinguir **"agotado"** de **"no lo tenemos"**, que
  comercialmente no es lo mismo.
- Si la consulta no nombra ningun producto (`"precio ps5"`), devuelve
  `termino: ""` y una nota para que el agente pida el titulo.

## `GET /products/agent-catalog`

Volcado plano de todo el catalogo, para cachearlo en local y consultarlo con
grep. Asi los precios durante una conversacion no cuestan ni una llamada de red.

```bash
curl -s -H "X-API-Key: $AGENT_API_KEY" \
  "$HG_API/products/agent-catalog" > bandeja/catalogo.json
```

El stock si cambia durante el dia: usa el cache para conversar y confirma con
`agent-search` antes de cerrar la venta.

## Verificado en produccion

Pese a los comentarios `# ajustar tabla/columna` de `app/models.py:36-38`, los
joins resuelven bien: una consulta real devolvio `"consola": "PlayStation 5"` y
`"licencia": "Secundaria"`, no `null`.

Esa misma prueba destapo las filas duplicadas por lote, que es de donde salio el
agrupado descrito arriba.
