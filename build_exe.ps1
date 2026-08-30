#Requires -Version 5.1
<#
.SYNOPSIS
  Build PDFSearchViewer as a standalone Windows .exe with PyInstaller.

.DESCRIPTION
  Uses the project virtualenv (.venv). Installs PyInstaller if missing,
  then builds a one-file, windowed executable.

.PARAMETER Clean
  Remove build/ and dist/ before packing.

.PARAMETER Onedir
  Build a folder distribution (faster startup) instead of a single .exe.

.EXAMPLE
  .\build_exe.ps1

.EXAMPLE
  .\build_exe.ps1 -Clean

.EXAMPLE
  .\build_exe.ps1 -Onedir
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Onedir
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtualenv .venv ..."
    python -m venv .venv
}

Write-Host "Using: $venvPython"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e .
& $venvPython -m pip install "pyinstaller>=6.3"

if ($Clean) {
    foreach ($dir in @("build", "dist")) {
        $p = Join-Path $PSScriptRoot $dir
        if (Test-Path $p) {
            Write-Host "Removing $dir ..."
            Remove-Item -Recurse -Force $p
        }
    }
}

$spec = Join-Path $PSScriptRoot "PDFSearchViewer.spec"
if ($Onedir) {
    Write-Host "Building onedir (folder) ..."
    & $venvPython -m PyInstaller --noconfirm --clean `
        --paths (Join-Path $PSScriptRoot "src") `
        --name PDFSearchViewer `
        --windowed `
        --collect-all pymupdf `
        --hidden-import pymupdf `
        --hidden-import fitz `
        --exclude-module pytest `
        --exclude-module tkinter `
        (Join-Path $PSScriptRoot "src\pdfsearchviewer\__main__.py")
    $out = Join-Path $PSScriptRoot "dist\PDFSearchViewer\PDFSearchViewer.exe"
} else {
    Write-Host "Building onefile exe from spec ..."
    & $venvPython -m PyInstaller --noconfirm --clean $spec
    $out = Join-Path $PSScriptRoot "dist\PDFSearchViewer.exe"
}

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $out)) {
    throw "Expected output not found: $out"
}

$sizeMb = [math]::Round((Get-Item $out).Length / 1MB, 1)
Write-Host ""
Write-Host "Done: $out ($sizeMb MB)"
Write-Host "Copy that file (or the whole dist\PDFSearchViewer folder if -Onedir) to run without Python."
