# Start FinAlly in Docker (Windows PowerShell). Idempotent: safe to run repeatedly.
# Usage: .\scripts\start_windows.ps1 [-Build] [-NoOpen]
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoOpen,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

$Image = 'finally:latest'
$Container = 'finally'
$Volume = 'finally-data'
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Test-DockerOk {
    param([string[]]$DockerArgs)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & docker @DockerArgs *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

if (-not (Test-DockerOk @('info'))) {
    Write-Error 'Docker is not running. Start Docker Desktop and try again.'
    exit 1
}

if ($Build -or -not (Test-DockerOk @('image', 'inspect', $Image))) {
    Write-Host "Building $Image..."
    & docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { Write-Error 'docker build failed.'; exit 1 }
}

$envArgs = @()
if (Test-Path (Join-Path $Root '.env')) {
    $envArgs = @('--env-file', '.env')
} else {
    Write-Warning '.env not found; AI chat needs OPENROUTER_API_KEY (see .env.example).'
}

# Replace any existing container (running or stopped); the volume is kept.
if (Test-DockerOk @('container', 'inspect', $Container)) {
    & docker stop $Container | Out-Null
    & docker rm $Container | Out-Null
}

& docker run -d --name $Container -p "${Port}:8000" -v "${Volume}:/app/db" @envArgs $Image | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error 'docker run failed.'; exit 1 }

Write-Host 'Waiting for FinAlly to become healthy...'
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if (-not $healthy) {
    Write-Error "FinAlly did not become healthy within 30s. Check: docker logs $Container"
    exit 1
}

Write-Host "FinAlly is running at $Url"

if (-not $NoOpen) {
    Start-Process $Url
}
