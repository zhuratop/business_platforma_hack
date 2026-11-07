param(
    [switch]$Lan,
    [ValidateRange(1,8)][int]$Workers = 2,
    [ValidateRange(1,65535)][int]$Port = 8000,
    [string]$PublicBaseUrl = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements.txt first (see README.md).' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Run npm ci and npm run build in frontend first.' }
$runRoot = if ($env:SPR_RUNTIME) { $env:SPR_RUNTIME } else { Join-Path $projectRoot 'runtime' }
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$listenAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
if ($PublicBaseUrl) { $env:PUBLIC_BASE_URL = $PublicBaseUrl.TrimEnd('/') }
$workerProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','backend.app.workers.main','--workers',"$Workers") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runRoot 'worker.stdout.log') -RedirectStandardError (Join-Path $runRoot 'worker.stderr.log')
try {
    Write-Host "SPR: http://127.0.0.1:$Port | parallel tasks: $Workers | Ctrl+C to stop API"
    if ($Lan) { Write-Host "LAN enabled: open http://<server IPv4>:$Port on another device. Use ipconfig to find the address." }
    & $pythonPath -m uvicorn backend.app.api:app --host $listenAddress --port $Port
} finally {
    if (-not $workerProcess.HasExited) { & taskkill /PID $workerProcess.Id /T /F | Out-Null }
}
