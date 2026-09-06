# Configura el contestador de bandeja en Windows.
#
# Se ejecuta como archivo a proposito: pegar un Read-Host en la consola no
# funciona, porque las lineas que vienen detras del pegado se cuelan como
# respuesta al prompt. Dentro de un script eso no pasa.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\configurar-bandeja.ps1

$ErrorActionPreference = "Stop"

$api = "https://api.hardcoregames.co"

Write-Host ""
Write-Host "Configuracion del contestador - Hardcore Games" -ForegroundColor Cyan
Write-Host ""
Write-Host "Necesito la AGENT_API_KEY del VPS. Sacala con:" -ForegroundColor Yellow
Write-Host "  grep '^AGENT_API_KEY=' /root/hc/hc-fastapi.env"
Write-Host ""

$clave = (Read-Host "Pega la clave y dale Enter").Trim()

if ([string]::IsNullOrWhiteSpace($clave)) {
    Write-Host "No pegaste nada. Vuelve a ejecutarlo." -ForegroundColor Red
    exit 1
}
if ($clave -match '^AGENT_API_KEY=') {
    # Copiaron la linea entera del grep en vez de solo el valor.
    $clave = $clave -replace '^AGENT_API_KEY=', ''
    Write-Host "  (le quite el AGENT_API_KEY= de delante)" -ForegroundColor DarkGray
}
if ($clave.Length -lt 32) {
    Write-Host "Esa clave parece incompleta ($($clave.Length) caracteres, se esperan 64)." -ForegroundColor Red
    Write-Host "Copiala otra vez completa y repite." -ForegroundColor Red
    exit 1
}

# Permanentes (sobreviven a cerrar la ventana) y activas ya en esta sesion.
[Environment]::SetEnvironmentVariable("HG_API", $api,    "User")
[Environment]::SetEnvironmentVariable("HG_KEY", $clave,  "User")
$env:HG_API = $api
$env:HG_KEY = $clave

Write-Host ""
Write-Host "Guardadas. Probando contra la API..." -ForegroundColor Cyan

$resp = curl.exe -s -o - -w "`n%{http_code}" "$api/products/agent-search?q=FC%2026" -H "X-API-Key: $clave"
$lineas = $resp -split "`n"
$codigo = $lineas[-1]
$cuerpo = ($lineas[0..($lineas.Count - 2)] -join "`n")

Write-Host ""
switch ($codigo) {
    "200" {
        Write-Host "LISTO. La API responde." -ForegroundColor Green
        Write-Host ($cuerpo.Substring(0, [Math]::Min(200, $cuerpo.Length))) -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Ya puedes arrancar:" -ForegroundColor Cyan
        Write-Host "  claude"
        Write-Host "  /loop 5m /bandeja"
    }
    "401" {
        Write-Host "La clave no es valida (401). Revisa que sea la que esta ahora en el VPS." -ForegroundColor Red
    }
    "503" {
        Write-Host "El servidor no tiene AGENT_API_KEY configurada (503)." -ForegroundColor Red
        Write-Host "Anadela a /root/hc/hc-fastapi.env y reinicia hc-fastapi." -ForegroundColor Red
    }
    default {
        Write-Host "Respuesta inesperada: $codigo" -ForegroundColor Red
        Write-Host $cuerpo -ForegroundColor DarkGray
    }
}
Write-Host ""
