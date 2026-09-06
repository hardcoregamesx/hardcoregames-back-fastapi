# Estado del contestador

Archivos que controlan y recuerdan el trabajo de la bandeja. El contexto de
Claude se borra; esto no.

| Archivo | Para qué |
|---|---|
| `MODO` | `real` o `prueba`. **Si falta, se asume `prueba`** (falla seguro). |
| `PAUSA` | Si existe, el contestador no hace nada. Freno de emergencia. |
| `estado.json` | Qué se atendió, qué se escaló, en canales sin estado propio. |
| `catalogo.json` | Volcado diario de precios. Se consulta con grep: cero red. |

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
