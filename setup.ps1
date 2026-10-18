$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '需要安装 Python 3.12 或更高版本，并将 python 加入 PATH。' }
}
& $pythonPath -c 'import sys; assert sys.version_info >= (3, 12), "Requires Python 3.12+"'
if ($LASTEXITCODE -ne 0) { throw 'Python 版本不满足要求。' }
& $pythonPath -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络与上方错误。' }
Write-Host '安装完成。运行 .\run.ps1 启动 MediaForge。'
