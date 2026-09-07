<#
Lista las conversaciones pendientes de Chatwoot por API, en una linea por
conversacion.

Existe porque leer la bandeja con el navegador costaba ~143.000 tokens y siete
minutos: el agente abria los chats uno por uno para saber quien habia escrito
ultimo. La API da ese dato de una.

    powershell -ExecutionPolicy Bypass -File .\scripts\chatwoot-pendientes.ps1

Necesita en el entorno:
    CHATWOOT_URL    https://chatwoot.srv936408.hstgr.cloud
    CHATWOOT_TOKEN  Perfil -> Configuracion del perfil -> Token de acceso
    CHATWOOT_CUENTA (opcional, por defecto 1)
#>
param(
    [string]$Estado = "open",
    [int]$Maximo = 25
)

$ErrorActionPreference = "Stop"

$base   = $env:CHATWOOT_URL
$token  = $env:CHATWOOT_TOKEN
$cuenta = if ($env:CHATWOOT_CUENTA) { $env:CHATWOOT_CUENTA } else { "1" }

if (-not $base -or -not $token) {
    Write-Output "ERROR: faltan CHATWOOT_URL o CHATWOOT_TOKEN en el entorno."
    Write-Output "El token se saca en Chatwoot: Perfil -> Configuracion del perfil -> Token de acceso."
    exit 1
}
$base = $base.TrimEnd('/')

try {
    $r = Invoke-RestMethod -Method Get `
        -Uri "$base/api/v1/accounts/$cuenta/conversations?status=$Estado" `
        -Headers @{ api_access_token = $token } `
        -TimeoutSec 30
} catch {
    Write-Output "ERROR consultando Chatwoot: $($_.Exception.Message)"
    Write-Output "Comprueba CHATWOOT_URL, el token y que la cuenta $cuenta exista."
    exit 1
}

# La forma de la respuesta cambia entre versiones de Chatwoot.
$conversaciones = $null
foreach ($ruta in @({ $r.data.payload }, { $r.payload }, { $r.data })) {
    $v = & $ruta 2>$null
    if ($v -and $v.Count -ge 0 -and $v -isnot [string]) { $conversaciones = $v; break }
}
if ($null -eq $conversaciones) {
    Write-Output "ERROR: no reconozco la forma de la respuesta. Primeros 400 caracteres:"
    Write-Output (($r | ConvertTo-Json -Depth 4).Substring(0, 400))
    exit 1
}

$n = 0
foreach ($c in $conversaciones) {
    if ($n -ge $Maximo) { break }

    $nombre   = $c.meta.sender.name
    if (-not $nombre) { $nombre = "(sin nombre)" }
    $telefono = $c.meta.sender.phone_number
    if (-not $telefono) { $telefono = $c.meta.sender.identifier }
    if (-not $telefono) { $telefono = "-" }

    # message_type 0 = entrante (cliente), 1 = saliente (nosotros)
    $ultimo = "?"
    $msg = $c.messages | Select-Object -Last 1
    if ($null -ne $msg) {
        if ($msg.message_type -eq 0) { $ultimo = "cliente" }
        elseif ($msg.message_type -eq 1) { $ultimo = "nosotros" }
    }

    $texto = $c.last_non_activity_message.content
    if (-not $texto -and $msg) { $texto = $msg.content }
    if (-not $texto) { $texto = "" }
    $texto = ($texto -replace '\s+', ' ').Trim()
    if ($texto.Length -gt 80) { $texto = $texto.Substring(0, 80) }

    $etiquetas = ""
    if ($c.labels -and $c.labels.Count -gt 0) { $etiquetas = " ETIQUETAS=" + ($c.labels -join ',') }

    Write-Output "chatwoot | $($c.id) | $telefono | $nombre | $texto | ULTIMO=$ultimo$etiquetas"
    $n++
}

if ($n -eq 0) { Write-Output "chatwoot | sin conversaciones $Estado" }
