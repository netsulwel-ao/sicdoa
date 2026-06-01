$taskName = 'SICDOA_GerarQuotas'
$scriptPath = 'C:\Users\Ramos Francisco\Downloads\sicdoa_version_python-master\run_gerar_quotas.ps1'

# Create the runner script
@"
Set-Location 'C:\Users\Ramos Francisco\Downloads\sicdoa_version_python-master'
& 'C:\Users\Ramos Francisco\AppData\Local\Programs\Python\Python312\python.exe' manage.py gerar_quotas --force
"@ | Set-Content -Path $scriptPath -Encoding UTF8

# Try Register-ScheduledJob
Unregister-ScheduledJob -Name $taskName -ErrorAction SilentlyContinue
$trigger = New-JobTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 3) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledJob -Name $taskName -ScriptBlock { & 'C:\Users\Ramos Francisco\Downloads\sicdoa_version_python-master\run_gerar_quotas.ps1' } -Trigger $trigger

Write-Host "Task '$taskName' created. Runs every 3 minutes."
