#Requires -Version 5.1
# Thin wrapper — the canonical build lives in package_core.py (deterministic zip).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Get-Command python3, python, py -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { throw "Python 3 is required (scripts/package_core.py is the canonical deterministic builder)." }
if ($py.Name -like "py*") { & $py.Source -3 package_core.py @args } else { & $py.Source package_core.py @args }
