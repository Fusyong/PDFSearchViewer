#Requires -Version 5.1
<#
.SYNOPSIS
  打包 PDFSearchViewer（默认文件夹，不压成单个 exe）。

.DESCRIPTION
  使用项目虚拟环境 .venv。依赖和 PyInstaller 已就绪时会跳过安装。
  默认 onedir：程序和依赖放在 dist\PDFSearchViewer\ 里，打包和启动都比单文件快。
  单文件 exe 仍可用 -Onefile 生成。

.PARAMETER Clean
  先删除 build\、dist\，并清空 PyInstaller 缓存后再打包。

.PARAMETER Onefile
  打成单个 dist\PDFSearchViewer.exe。拷贝方便，但打包更慢，每次启动都要解压。

.PARAMETER Onedir
  与默认相同，保留此参数以便旧命令继续可用。

.EXAMPLE
  .\build_exe.ps1

.EXAMPLE
  .\build_exe.ps1 -Clean

.EXAMPLE
  .\build_exe.ps1 -Onefile
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Onefile,
    [switch]$Onedir
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if ($Onefile -and $Onedir) {
    throw "不能同时使用 -Onefile 和 -Onedir。"
}

$mode = if ($Onefile) { "onefile" } else { "onedir" }
$env:PDFSV_ONEFILE = if ($Onefile) { "1" } else { "0" }

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "正在创建虚拟环境 .venv ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "创建虚拟环境失败（退出码 $LASTEXITCODE）。请确认已安装 Python 3.11+ 并在 PATH 中。"
    }
}

Write-Host "使用: $venvPython"

& $venvPython -c "import PySide6, pymupdf, PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "正在安装运行依赖和 PyInstaller ..."
    & $venvPython -m pip install --disable-pip-version-check -e ".[packaging]"
    if ($LASTEXITCODE -ne 0) {
        throw "pip install 失败（退出码 $LASTEXITCODE）。"
    }
} else {
    Write-Host "依赖已就绪，跳过 pip 安装。"
}

if ($Clean) {
    foreach ($dir in @("build", "dist")) {
        $p = Join-Path $PSScriptRoot $dir
        if (Test-Path -LiteralPath $p) {
            Write-Host "正在删除 $dir ..."
            Remove-Item -LiteralPath $p -Recurse -Force
        }
    }
}

$spec = Join-Path $PSScriptRoot "PDFSearchViewer.spec"
$work = Join-Path $PSScriptRoot "build\$mode"
$dist = Join-Path $PSScriptRoot "dist"

$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm"
)
if ($Clean) {
    $pyiArgs += "--clean"
}
$pyiArgs += @(
    "--workpath", $work,
    "--distpath", $dist,
    $spec
)

if ($mode -eq "onedir") {
    Write-Host "正在打包为文件夹（不压缩成单个 exe）..."
    $out = Join-Path $dist "PDFSearchViewer\PDFSearchViewer.exe"
} else {
    Write-Host "正在打包为单个 exe（较慢）..."
    $out = Join-Path $dist "PDFSearchViewer.exe"
}

$timer = [Diagnostics.Stopwatch]::StartNew()
& $venvPython @pyiArgs
$timer.Stop()
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 失败（退出码 $LASTEXITCODE）。"
}

if (-not (Test-Path -LiteralPath $out)) {
    throw "未找到预期产物: $out"
}

$seconds = [math]::Round($timer.Elapsed.TotalSeconds, 1)
Write-Host ""
Write-Host "完成，用时 $seconds 秒"
Write-Host "运行: $out"

if ($mode -eq "onedir") {
    $folder = Join-Path $dist "PDFSearchViewer"
    $sum = (Get-ChildItem -LiteralPath $folder -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $sizeMb = [math]::Round(($sum / 1MB), 1)
    Write-Host "目录: $folder ($sizeMb MB)"
    Write-Host "请拷贝整个文件夹。只拷贝其中的 exe 无法运行。"
} else {
    $sizeMb = [math]::Round(((Get-Item -LiteralPath $out).Length / 1MB), 1)
    Write-Host "文件: $out ($sizeMb MB)"
}
