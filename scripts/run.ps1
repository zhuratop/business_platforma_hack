$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements.txt first (see README.md).' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Run npm ci and npm run build in frontend first.' }
$runRoot = if ($env:SPR_RUNTIME) { $env:SPR_RUNTIME } else { Join-Path $projectRoot 'runtime' }
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$workerProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','backend.app.workers.main') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runRoot 'worker.stdout.log') -RedirectStandardError (Join-Path $runRoot 'worker.stderr.log')
try {
    Write-Host 'SPR: http://127.0.0.1:8000 | alice/demo and bob/demo | Ctrl+C to stop API'
    & $pythonPath -m uvicorn backend.app.api:app --host 127.0.0.1 --port 8000
} finally {
    if (-not $workerProcess.HasExited) { & taskkill /PID $workerProcess.Id /T /F | Out-Null }
}
