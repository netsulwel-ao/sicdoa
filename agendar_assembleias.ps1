# ═══════════════════════════════════════════════════════════════
# agendar_assembleias.ps1
# Agenda no Windows Task Scheduler para iniciar assembleias
# automaticamente quando a data/hora agendada chegar.
# ═══════════════════════════════════════════════════════════════

$ProjectPath = "C:\Users\Ramos Francisco\Documents\projects\sicdoa"
$PythonExe = "python"
$Command = "manage.py iniciar_assembleias"
$TaskName = "CDOA-IniciarAssembleias"
$ScriptPath = Join-Path $ProjectPath "run_iniciar_assembleias.bat"

# Criar .bat para executar o management command
@"
@echo off
cd /d "$ProjectPath"
$PythonExe $Command
"@ | Out-File -FilePath $ScriptPath -Encoding ASCII

# Criar tarefa agendada (corre a cada 5 minutos)
$Action = New-ScheduledTaskAction -Execute $ScriptPath
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force

Write-Host "Tarefa '$TaskName' criada com sucesso! Corre a cada 5 minutos."
Write-Host "Para testar manualmente: $PythonExe $ProjectPath\$Command"
