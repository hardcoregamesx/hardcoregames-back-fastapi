# Estado del contestador

Archivos que controlan y recuerdan el trabajo de la bandeja. El contexto de
Claude se borra; esto no.

| Archivo | Para qué |
|---|---|
| `MODO` | `real` o `prueba`. **Si falta, se asume `prueba`** (falla seguro). |
| `PAUSA` | Si existe, el contestador no hace nada. Freno de emergencia. |
| `estado.json` | Qué se atendió, qué se escaló, en canales sin estado propio. |
| `catalogo.json` | Volcado diario de precios. Se consulta con grep: cero red. |
| `enviados.log` | Una línea por mensaje enviado. Solo se añade. Es el único rastro de lo que salió. |
| `canales.txt` | Qué canales atiende y en qué orden. Chatwoot siempre primero. |

## Los dos canales, cada vuelta

Se atienden Chatwoot y WhatsApp en cada vuelta, uno detrás de otro — nunca a
la vez, porque hay un solo navegador y las pestañas se pisan.

Chatwoot va primero a propósito: de su lista se sacan los nombres y teléfonos
que luego se descartan en WhatsApp, para que un cliente que escribe por los
dos sitios no reciba dos respuestas distintas. Si Chatwoot falla, WhatsApp se
salta esa vuelta: duplicar es peor que esperar.

Tope de 6 chats por canal y vuelta. Una vuelta cargada tarda más de 5 minutos;
la siguiente arranca cuando termine, no se solapan.

## Revisar qué se envió

    Get-Content bandeja\enviados.log -Tail 30      # Windows
    tail -30 bandeja/enviados.log                  # Linux/Mac

El contestador no narra los mensajes en el chat, así que este archivo es la
forma de auditarlo.

## Uso

    echo prueba > bandeja/MODO     # redacta pero no envía
    echo real   > bandeja/MODO     # envía de verdad
    touch bandeja/PAUSA            # PARAR TODO ahora
    rm bandeja/PAUSA               # reanudar

## Correrlo solo

    /loop 5m /bandeja

Cada vuelta revisa la bandeja. Las vueltas vacías cuestan poco; el trabajo de
verdad ocurre dentro de subagentes que mueren al terminar, así que el contexto
no se llena aunque corra horas.

Necesita `HG_API` y `HG_KEY` en el entorno:

    export HG_API=https://api.hardcoregames.co
    export HG_KEY=<la clave del VPS>
