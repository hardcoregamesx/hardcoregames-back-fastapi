# Guarda las credenciales de Chatwoot en el usuario de Windows y prueba la API.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\configurar-chatwoot.ps1

$ErrorActionPreference = "Stop"
$url = "https://chatwoot.srv936408.hstgr.cloud"

Write-Host ""
Write-Host "Configuracion de Chatwoot" -ForegroundColor Cyan
Write-Host ""
Write-Host "El token se saca asi:" -ForegroundColor Yellow
Write-Host "  1. Entra a $url"
Write-Host "  2. Clic en tu foto (abajo a la izquierda) -> Configuracion del perfil"
Write-Host "  3. Baja hasta 'Token de acceso' y copialo"
Write-Host ""

$token = (Read-Host "Pega el token y dale Enter").Trim()
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "No pegaste nada. Vuelve a ejecutarlo." -ForegroundColor Red
    exit 1
}

[Environment]::SetEnvironmentVariable("CHATWOOT_URL",   $url,   "User")
[Environment]::SetEnvironmentVariable("CHATWOOT_TOKEN", $token, "User")
$env:CHATWOOT_URL = $url
$env:CHATWOOT_TOKEN = $token

Write-Host ""
Write-Host "Guardado. Probando..." -ForegroundColor Cyan
Write-Host ""
& "$PSScriptRoot\chatwoot-pendientes.ps1"
Write-Host ""
Write-Host "Si arriba ves conversaciones (o 'sin conversaciones open'), esta listo." -ForegroundColor Green
Write-Host "Reinicia Claude Desktop para que coja las variables nuevas." -ForegroundColor Yellow
