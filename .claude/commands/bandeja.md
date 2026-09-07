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

## UN CANAL POR VUELTA (turnos)
Hay un solo navegador: si un subagente abre WhatsApp Web, la pestaña deja
Chatwoot y el siguiente no encuentra nada. Por eso cada vuelta atiende UN
canal y se van turnando.

1. Lee `bandeja/canales.txt` (un canal por línea, ignora líneas con `#`).
2. Lee `bandeja/turno`: el canal que toca. Si no existe o no está en la lista,
   empieza por el primero.
3. Atiende SOLO ese canal.
4. Al terminar, escribe en `bandeja/turno` el SIGUIENTE de la lista (y vuelve
   al primero cuando llegues al final). Hazlo aunque no hubiera nada que
   atender, o te quedas atascado en un canal vacío.

Si en $ARGUMENTS viene un canal, atiende ese y NO toques el turno: es una
petición puntual, no la rotación normal.

## PROCESO
1. Un subagente `chat-chrome` en modo LISTAR del canal que toca por turno.
2. Aplica el TRIAGE de la skill sobre esa lista, sin abrir nada.
3. Por cada chat que SÍ necesita respuesta, de uno en uno: un subagente
   `chat-chrome` en modo ATENDER. Espera a que termine antes del siguiente.
4. **Máximo 10 chats por vuelta.** Si quedan más, dilo y déjalos para la
   siguiente: la bandeja sigue ahí.
5. Muestra solo las líneas de resultado.

## AL CERRAR
Una línea de resumen, nombrando el canal y cuál sigue:
`chatwoot: N atendidos · N escalados · N saltados (motivo) · siguiente: whatsapp`

Si no había nada que hacer, di solo "sin novedad" y termina. No inventes
trabajo para justificar la vuelta.
