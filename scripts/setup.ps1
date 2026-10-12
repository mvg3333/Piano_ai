param([switch]$WithModel)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$projectRoot = $PWD.Path
New-Item -ItemType Directory -Force .tools | Out-Null
$uv = Join-Path $projectRoot '.tools\uv\bin\uv.exe'
if (!(Test-Path -LiteralPath $uv)) {
    python -m pip install --target .tools/uv uv==0.13.0
    if ($LASTEXITCODE) { throw 'uv installation failed. Install Python from python.org first.' }
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.tools\python'
$env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
& $uv python install 3.11.17 --no-bin
if ($LASTEXITCODE) { throw 'Python 3.11 installation failed.' }
if (!(Test-Path .venv/Scripts/python.exe)) { & $uv venv --python 3.11.17 .venv }
& $uv pip sync backend/requirements.lock --python .venv/Scripts/python.exe
if ($LASTEXITCODE) { throw 'Backend dependency installation failed.' }
$nodeVersion = 'v24.21.0'
$nodeDirectory = Join-Path $projectRoot ".tools\node-$nodeVersion-win-x64"
if (!(Test-Path "$nodeDirectory\node.exe")) {
    $zipName = "node-$nodeVersion-win-x64.zip"
    Invoke-WebRequest "https://nodejs.org/dist/$nodeVersion/$zipName" -OutFile ".tools/$zipName"
    $checksums = (Invoke-WebRequest "https://nodejs.org/dist/$nodeVersion/SHASUMS256.txt").Content
    $expected = (($checksums -split "`n" | Where-Object { $_ -match [regex]::Escape($zipName) }) -split '\s+')[0]
    if ((Get-FileHash ".tools/$zipName" -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Node download checksum mismatch.' }
    Expand-Archive ".tools/$zipName" .tools -Force
}
$env:PATH = "$nodeDirectory;" + $env:PATH
npm.cmd --prefix frontend ci
if ($LASTEXITCODE) { throw 'Frontend installation failed.' }
if ($WithModel) {
    if (!(Test-Path .venv-model/Scripts/python.exe)) { & $uv venv --python 3.11.17 .venv-model }
    & $uv pip sync backend/model-requirements.lock --python .venv-model/Scripts/python.exe
    if ($LASTEXITCODE) { throw 'Model installation failed. Demo and MIDI can still run.' }
}
& ./.venv/Scripts/python.exe -m backend.demo
if ($LASTEXITCODE) { throw 'Demo generation failed.' }
npm.cmd --prefix frontend run build
if ($LASTEXITCODE) { throw 'Frontend build failed.' }
& ./.venv/Scripts/python.exe -m scripts.doctor
Write-Host 'Ready. Run .\scripts\run.ps1, then open http://localhost:8000'
