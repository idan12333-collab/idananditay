# Sets up the Python environment (first run only) and starts the local app.
# The environment lives in %USERPROFILE%\.ai-photo-album\venv (outside OneDrive).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$home_dir = Join-Path $env:USERPROFILE ".ai-photo-album"
$venv = Join-Path $home_dir "venv"
$py = Join-Path $venv "Scripts\python.exe"
$req = Join-Path $root "requirements-dev.txt"
$stamp = Join-Path $venv "requirements.stamp"

if (-not (Test-Path $py)) {
    Write-Host "Creating Python 3.12 environment (first run)..."
    py -3.12 -m venv $venv
    if (-not $?) { throw "Python 3.12 not found. Install it from https://www.python.org/downloads/" }
}

$reqHash = (Get-FileHash (Join-Path $root "requirements.txt")).Hash + (Get-FileHash $req).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $reqHash) {
    Write-Host "Installing dependencies..."
    & $py -m pip install --disable-pip-version-check -q -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    Set-Content -Path $stamp -Value $reqHash
}

Set-Location $root
if ($args -contains "--test") {
    & $py -m pytest -p no:cacheprovider
    exit $LASTEXITCODE
}
Write-Host ""
# The server opens the browser itself, and only once it is really serving. If an older copy
# of the app is still running it refuses to start and says so (ADR-013).
& $py -m app serve --open-browser
