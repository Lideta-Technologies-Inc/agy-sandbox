<#
.SYNOPSIS
    agy-sandbox: Cross-platform wrapper script for the agy-sandbox Python package on Windows.

.DESCRIPTION
    This script provides backward compatibility with the original manage-agy.sh on Windows
    using PowerShell. It calls the agy-sandbox Python CLI.

.EXAMPLE
    .\agy-sandbox.ps1 ..\custodian-kernel vertex
    .\agy-sandbox.ps1 C:\path\to\project
#>

param(
    [Parameter(Position = 0)]
    [string]$ProjectDir = ".",

    [Parameter(Position = 1)]
    [ValidateSet("studio", "vertex")]
    [string]$Provider = "studio"
)

$ErrorActionPreference = "Stop"

# Find the agy-sandbox command
$agyCmd = $null

# Try Python directly first
$pythonExe = Get-Command python -ErrorAction SilentlyContinue
if ($pythonExe) {
    $pythonPath = $pythonExe.Source
    $agyScript = Join-Path (Split-Path $pythonPath -Parent) "agy-sandbox.exe" -ErrorAction SilentlyContinue
    if (Test-Path $agyScript) {
        $agyCmd = $agyScript
    }
}

# Try agy-sandbox in PATH
if (-not $agyCmd) {
    $agyInPath = Get-Command agy-sandbox -ErrorAction SilentlyContinue
    if ($agyInPath) {
        $agyCmd = $agyInPath.Source
    }
}

if (-not $agyCmd) {
    Write-Error "agy-sandbox command not found."
    Write-Error "Please install it with: pip install agy-sandbox"
    exit 1
}

# Resolve project directory to absolute path
if (-not [System.IO.Path]::IsPathRooted($ProjectDir)) {
    $ProjectDir = Join-Path (Get-Location) $ProjectDir
}
$ProjectDir = (Resolve-Path $ProjectDir -ErrorAction SilentlyContinue).Path

if (-not (Test-Path $ProjectDir)) {
    Write-Error "Project directory '$ProjectDir' does not exist."
    exit 1
}

# Run the Python CLI
& $agyCmd provision $ProjectDir --provider $Provider
$exitCode = $LASTEXITCODE
exit $exitCode