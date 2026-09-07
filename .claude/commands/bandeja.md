---
description: Atiende la bandeja de chats sin llenar el contexto. Pensado para correr en loop.
---

Sigue la skill `bandeja-hardcore`.

## ANTES DE NADA
1. Si existe `bandeja/PAUSA` → responde "en pausa" y termina. Nada más.
2. Lee `bandeja/MODO`. Si no existe, es `prueba` y lo dices al empezar.
3. Si `bandeja/catalogo.json` falta o es de otro día, refréscalo:
   `curl -s "$HG_API/products/agent-catalog" -H "X-API-Key: $HG_KEY" > bandeja/catalogo.json`

## REGLAS DEL HILO PRINCIPAL (tú)
- NO abras el navegador. Nunca. Ni una mirada, ni una captura.
- Todo contacto con el navegador va dentro de un subagente `chat-chrome`.
- Los subagentes van EN SERIE, uno a la vez. Hay un solo navegador: si lanzas
  varios se pelean por las pestañas y contestan chats cruzados.

## LOS DOS CANALES, CADA VUELTA
Se atienden Chatwoot y WhatsApp Web en cada vuelta, uno detrás de otro. Nunca
a la vez: hay un solo navegador y las pestañas se pisan.

El orden es fijo y no se cambia: **Chatwoot primero, WhatsApp después.**
Chatwoot es el que manda para descartar clientes repetidos.

Los canales están en `bandeja/canales.txt`, uno por línea (ignora las que
empiezan por `#`). Si solo hay uno, haces solo ese.

## PROCESO

### Fase A — Chatwoot
1. Un subagente **`chat-listar`** con el canal `chatwoot`. Es barato y no
   abre chats: si tarda minutos o gasta más de 20k tokens, algo va mal
   y hay que decirlo.
2. De esa lista guarda el NOMBRE y el TELÉFONO de **todas** las
   conversaciones, incluidas las que vas a saltar en el triage. Esa lista es
   lo único que evita responderle dos veces al mismo cliente.
3. Aplica el TRIAGE sobre esa lista, **sin abrir nada**, y atiende solo las
   que lo necesiten: **máximo 6**, un subagente `chat-chrome` cada una,
   en serie.
   Una fila con `ULTIMO=?` no es motivo para abrirla: mírala solo si el
   texto visible parece una pregunta sin responder.

### Fase B — WhatsApp Web
4. Un subagente **`chat-listar`** con el canal `whatsapp`.
5. **DESCARTA todo chat cuyo nombre o número aparezca en la lista de la fase
   A.** Ese cliente ya entra por Chatwoot; contestarle también aquí le manda
   dos respuestas distintas de dos sitios.
   Al comparar números ignora espacios, guiones, paréntesis y el prefijo +57:
   `+57 317 443 1627`, `3174431627` y `57 317 4431627` son el mismo cliente.
6. Triage sobre lo que quede y atiende con `chat-chrome`, **máximo 6**.

### Si Chatwoot falla
Si la fase A no se pudo hacer (no cargó, sesión caída), **NO hagas la fase B**.
Sin la lista de Chatwoot no puedes descartar repetidos, y duplicar respuestas
es peor que esperar cinco minutos. Dilo en una línea y termina.

## REGLAS DEL HILO PRINCIPAL (tú)
- NO abras el navegador. Nunca. Todo va dentro de subagentes `chat-chrome`.
- Los subagentes van EN SERIE, uno a la vez.
- Una vuelta con muchos chats tardará más de 5 minutos. Es normal: la
  siguiente arranca cuando termine esta, no se solapan.

## AL CERRAR
Una línea por canal:
`chatwoot: N atendidos · N escalados · N saltados`
`whatsapp: N atendidos · N escalados · N saltados · N descartados por estar en Chatwoot`

Si no hubo nada que hacer, "sin novedad" y termina.

Si no había nada que hacer, di solo "sin novedad" y termina. No inventes
trabajo para justificar la vuelta.
