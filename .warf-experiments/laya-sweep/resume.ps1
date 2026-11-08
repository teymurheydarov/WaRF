# Restart the Laya sweep after a reboot or a stop: start laya-serve if it is not
# answering (multilingual checkpoint only, 127.0.0.1:8000), wait for it, then run
# tools/run_laya_sweep.py, which resumes where it stopped. Appends to run.log.
#
#   powershell -ExecutionPolicy Bypass -File C:\workdir\warf\WaRF\.warf-experiments\laya-sweep\resume.ps1
#
# Stop the sweep gracefully by creating the file STOP next to this script.

$ErrorActionPreference = 'Stop'
$sweepHome = $PSScriptRoot
$python = 'C:\workdir\claudeVersuch\gs\cf\python.exe'
$warf = 'C:\workdir\warf\WaRF'

function Test-Laya {
    try { (Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5).status -eq 'ok' } catch { $false }
}

if (-not (Test-Laya)) {
    $env:LAYA_HOST = '127.0.0.1'
    $env:LAYA_PORT = '8000'
    $env:LAYA_MODELS = 'multilingual'
    $env:LAYA_LOG_LEVEL = 'warning'
    $env:HF_HUB_OFFLINE = '1'
    Start-Process -FilePath 'C:\workdir\warf\laya-venv\Scripts\laya-serve.exe' -WindowStyle Hidden `
        -RedirectStandardOutput "$sweepHome\laya-serve.out.log" -RedirectStandardError "$sweepHome\laya-serve.err.log"
    Write-Host 'laya-serve starting (about a minute) ...'
    $t0 = Get-Date
    while (-not (Test-Laya)) {
        if (((Get-Date) - $t0).TotalMinutes -gt 20) { throw "laya-serve did not come up in 20 minutes; see $sweepHome\laya-serve.err.log" }
        Start-Sleep -Seconds 5
    }
}
Write-Host 'laya-serve is up; resuming the sweep (progress in run.log, counts with: run_laya_sweep.py status)'
$env:PYTHONIOENCODING = 'utf-8'
cmd /c "cd /d `"$warf`" && `"$python`" tools\run_laya_sweep.py run --status-every 300 >> `"$sweepHome\run.log`" 2>&1"
Write-Host "sweep exited with code $LASTEXITCODE"
