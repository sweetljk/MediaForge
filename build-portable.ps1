$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe scripts/package_portable.py
if ($LASTEXITCODE -ne 0) { throw '完整便携版构建失败，请检查输出。' }
Write-Host '完成：release\MediaForge-0.1.0-windows-x64-portable.zip'
