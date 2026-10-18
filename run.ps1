$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host '请先运行 .\setup.ps1 安装 Python 依赖。'
    exit 1
}
& $pythonPath -m mediaforge @args
exit $LASTEXITCODE
