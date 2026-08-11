# Alternative dev path (no Docker build/rebuild) for fast iteration on this laptop only.
# Primary path is `docker compose up` (see README.md) — this script is not the source of
# truth for how to start the stack, just a quicker inner loop when editing asr-suggest.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "venv tidak ditemukan. Jalankan dulu:" -ForegroundColor Yellow
    Write-Host "  D:\laragon\bin\python\python-3.10\python.exe -m venv .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r services\asr-suggest\requirements.txt"
    exit 1
}

Write-Host "ASR      -> http://127.0.0.1:8000/health" -ForegroundColor Cyan
Write-Host "Frontend -> http://127.0.0.1:5500" -ForegroundColor Cyan

Start-Process -FilePath $py -ArgumentList "-m","uvicorn","app:app","--host","127.0.0.1","--port","8000" -WorkingDirectory (Join-Path $root "services\asr-suggest")
Start-Process -FilePath $py -ArgumentList "-m","http.server","5500","--bind","127.0.0.1" -WorkingDirectory (Join-Path $root "frontend")
Start-Process "http://127.0.0.1:5500"
