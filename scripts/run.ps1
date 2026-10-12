param([int]$Port=8000)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$nodeDirectory = Join-Path $PWD '.tools\node-v24.21.0-win-x64'
$env:PATH = "$nodeDirectory;" + $env:PATH
$env:PIANO_NODE = Join-Path $nodeDirectory 'node.exe'
& ./.venv/Scripts/python.exe -m scripts.run --port $Port
