#Requires -Version 5.1
<#
.SYNOPSIS
  Install skills into a project (.claude\skills) or personally (~\.claude\skills).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Target C:\code\myapp
  # all skills -> C:\code\myapp\.claude\skills

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Target C:\code\myapp rails-8
  # one skill -> project

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Global
  # all skills -> ~\.claude\skills (available in every project)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Global hotwire
#>
[CmdletBinding()]
param(
  [string]$Target = ".",
  [switch]$Global,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Skills = @()
)

$ErrorActionPreference = "Stop"

$src = Resolve-Path (Join-Path $PSScriptRoot "..\skills")
$available = Get-ChildItem -Directory $src | Select-Object -ExpandProperty Name

foreach ($s in $Skills) {
  if ($available -notcontains $s) {
    throw "Unknown skill '$s'. Available: $($available -join ', '). (Destination goes in -Target <dir>.)"
  }
}

if ($Global) {
  $dest = Join-Path $HOME ".claude\skills"
} else {
  $dest = Join-Path (Resolve-Path $Target) ".claude\skills"
}
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$installed = 0
foreach ($skill in (Get-ChildItem -Directory $src)) {
  $name = $skill.Name
  if ($Skills.Count -gt 0 -and $Skills -notcontains $name) { continue }
  $targetPath = Join-Path $dest $name
  if (Test-Path $targetPath) { Remove-Item -Recurse -Force $targetPath }
  Copy-Item -Recurse -Path $skill.FullName -Destination $targetPath
  Write-Host "installed: $name -> $targetPath"
  $installed++
}

if ($installed -eq 0) { throw "No matching skills found in $src" }

Write-Host ""
Write-Host "Done. If this skills directory didn't exist when your Claude Code session"
Write-Host "started, restart Claude Code so it can be watched; otherwise changes are"
Write-Host "picked up live. Verify inside Claude Code: 'what skills are available?'"
