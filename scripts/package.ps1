#Requires -Version 5.1
<#
.SYNOPSIS
  Rebuild dist\<name>.skill archives (zip of each skill folder) after editing skills\.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\package.ps1
#>
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null

# Use .NET directly (not Compress-Archive) so zip entries get proper
# forward-slash paths that every consumer of .skill files accepts.
Add-Type -AssemblyName System.IO.Compression.FileSystem

foreach ($skill in (Get-ChildItem -Directory (Join-Path $root "skills"))) {
  $name = $skill.Name
  $out  = Join-Path $dist "$name.skill"
  if (Test-Path $out) { Remove-Item -Force $out }
  [System.IO.Compression.ZipFile]::CreateFromDirectory(
    $skill.FullName,
    $out,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true   # include the skill folder itself as the zip's root entry
  )
  Write-Host "packaged: dist\$name.skill"
}
