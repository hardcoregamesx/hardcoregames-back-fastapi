# Endpoints para el agente de chats

Dos endpoints pensados para que un agente de IA cotice por WhatsApp, Chatwoot o
Marketplace sin abrir el navegador ni conectarse a Postgres.

## Por que no sirve `/products/search`

`/products/search` esta hecho para la grilla de la web, no para cotizar:

| | `/products/search` | `/products/agent-search` |
|---|---|---|
| Precio | el **minimo** del producto | el de **cada variante** |
| Stock | no lo devuelve | si |
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

## `GET /products/agent-search`

```bash
curl -s -H "X-API-Key: $AGENT_API_KEY" \
  "$HG_API/products/agent-search?q=FC%2027%20para%20PS5"
```

```json
{
  "q": "FC 27 para PS5",
  "termino": "fc27",
  "plataformas": ["playstation5"],
  "resultados": [
    {"producto": "FC 27 Standard", "consola": "PS5", "licencia": "Primaria",
     "precio": 180000, "precio_descuento": 160000, "stock": 3}
  ],
  "agotados_ocultos": 1
}
```

Parametros: `q` (requerido), `only_stock` (por defecto `true`), `limit` (25).

Notas de comportamiento:

- **La plataforma se extrae de la consulta y no contamina la busqueda.**
  `"FC 27 para PS5"` busca `fc27` y usa `PS5` para elegir la fila. Es el fallo
  que tiene `/products/search`, donde esa misma consulta devuelve cero filas.
- Si la plataforma no casa con ninguna fila, se devuelven **todas** en vez de un
  "no disponible" falso: es mejor ofrecer otra consola que negar el producto.
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

## Pendiente de verificar contra la BD real

`app/models.py:36-38` marca los FK de `GameDetail` con comentarios
`# ajustar tabla/columna`, asi que esos nombres pueden no coincidir con la base
de produccion. Antes de dar los endpoints por buenos, ejecuta una consulta real
y comprueba que `consola` y `licencia` vienen rellenos. Si llegan en `null`, el
join esta mal y hay que corregir los nombres de columna.
