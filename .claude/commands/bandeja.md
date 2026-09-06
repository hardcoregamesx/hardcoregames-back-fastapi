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

## PROCESO
1. Un subagente `chat-chrome` en modo LISTAR por canal: $ARGUMENTS
   (si no se indica ninguno: Chatwoot).
2. Aplica el TRIAGE de la skill sobre esa lista, sin abrir nada.
3. Por cada chat que SÍ necesita respuesta, de uno en uno: un subagente
   `chat-chrome` en modo ATENDER. Espera a que termine antes del siguiente.
4. **Máximo 10 chats por vuelta.** Si quedan más, dilo y déjalos para la
   siguiente: la bandeja sigue ahí.
5. Muestra solo las líneas de resultado.

## AL CERRAR
Una línea de resumen:
`N atendidos · N escalados · N saltados (motivo) · N pendientes para la próxima`

Si no había nada que hacer, di solo "sin novedad" y termina. No inventes
trabajo para justificar la vuelta.
