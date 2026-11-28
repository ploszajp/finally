# Stop and remove the FinAlly container (Windows PowerShell). The finally-data
# volume is kept, so the portfolio persists. Idempotent.
$ErrorActionPreference = 'Stop'

$Container = 'finally'

$old = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
& docker container inspect $Container *> $null
$exists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $old

if ($exists) {
    & docker stop $Container | Out-Null
    & docker rm $Container | Out-Null
    Write-Host "FinAlly stopped. Data volume 'finally-data' kept."
} else {
    Write-Host 'FinAlly is not running.'
}
exit 0
