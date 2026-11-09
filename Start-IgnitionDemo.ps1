param([int]$Port = 8766, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path $PSScriptRoot '.venv-demo/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw 'The demo environment is missing. Follow ignition_demo/README.md to set it up.'
}
$demoArguments = @('-m', 'scripts.ignition_demo.server', '--port', "$Port")
if (-not $NoBrowser) { $demoArguments += '--open' }
& $demoPython @demoArguments
if ($LASTEXITCODE -ne 0) { throw 'The demo could not start. Read the message above for the required recovery step.' }
