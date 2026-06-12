<#
.SYNOPSIS
    Script de backup manual da base de dados SICDOA.
.DESCRIPTION
    Executa o management command backup_db para criar um backup completo da
    base de dados MySQL, comprimir e enviar por email.
.EXAMPLE
    .\backup.ps1                  # Cria backup e envia email
    .\backup.ps1 -NoEmail         # Cria backup sem enviar email
#>

param(
    [switch]$NoEmail
)

$ProjectDir = Split-Path -Parent $PSScriptRoot
$ManagePy = Join-Path $ProjectDir "manage.py"

Write-Host "=== SICDOA - Backup Manual ===" -ForegroundColor Cyan
Write-Host "Projecto: $ProjectDir"
Write-Host ""

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python não encontrado no PATH."
    exit 1
}

$args = @("manage.py", "backup_db")
if ($NoEmail) {
    $args += "--no-email"
}

Set-Location -LiteralPath $ProjectDir
python @args

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Backup concluído com sucesso!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "✗ Backup falhou (código: $LASTEXITCODE)" -ForegroundColor Red
}
