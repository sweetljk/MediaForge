$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm MediaForge.spec
if ($LASTEXITCODE -ne 0) { throw '打包失败，请检查构建输出。' }
Write-Host '构建完成：dist\MediaForge\MediaForge.exe。请分发整个 MediaForge 目录。外部转换工具不捆绑。'
