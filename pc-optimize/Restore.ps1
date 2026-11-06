<#
  Undo everything Optimize.ps1 changed, using %ProgramData%\PingFpsTweak\backup.json.
#>
$ErrorActionPreference = 'Stop'

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    try {
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    } catch {
        Write-Host 'Әкімші (Administrator) рұқсаты керек. Қайта іске қосып, терезеде «Иә» бас.' -ForegroundColor Red
        Read-Host 'Enter бас'
    }
    exit
}

$Host.UI.RawUI.WindowTitle = 'Ping + FPS optimization - restore'
$BackupDir  = Join-Path $env:ProgramData 'PingFpsTweak'
$BackupFile = Join-Path $BackupDir 'backup.json'
$Balanced   = '381b4222-f694-41f0-9685-ff5bb260df2e'

function Convert-RegValue {
    param([string]$Kind, $Value)
    switch ($Kind) {
        'DWord'       { return [int]$Value }
        'QWord'       { return [long]$Value }
        'Binary'      { return , ([byte[]]@($Value)) }
        'MultiString' { return , ([string[]]@($Value)) }
        default       { return [string]$Value }
    }
}

Clear-Host
Write-Host '=============================================' -ForegroundColor Cyan
Write-Host '   БАСТАПҚЫ БАПТАУЛАРДЫ ҚАЙТАРУ' -ForegroundColor Cyan
Write-Host '=============================================' -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $BackupFile)) {
    Write-Host 'Резерв табылмады — қайтаратын ештеңе жоқ.' -ForegroundColor Yellow
    Read-Host 'Enter бас'
    exit
}

$b = Get-Content -LiteralPath $BackupFile -Raw -Encoding UTF8 | ConvertFrom-Json
$ok = 0
$fail = 0

# registry
foreach ($e in @($b.Registry)) {
    if (-not $e) { continue }
    try {
        if ($e.Existed) {
            if (-not (Test-Path -LiteralPath $e.Path)) { New-Item -Path $e.Path -Force | Out-Null }
            New-ItemProperty -LiteralPath $e.Path -Name $e.Name -PropertyType $e.Kind `
                -Value (Convert-RegValue $e.Kind $e.Value) -Force | Out-Null
        } elseif (Test-Path -LiteralPath $e.Path) {
            Remove-ItemProperty -LiteralPath $e.Path -Name $e.Name -ErrorAction SilentlyContinue
        }
        $ok++
    } catch {
        Write-Host "   [!] $($e.Path)\$($e.Name): $($_.Exception.Message)" -ForegroundColor Yellow
        $fail++
    }
}
Write-Host "   Реестр: $ok мән қайтарылды"

# power plan
try {
    $target = if ($b.PowerScheme) { $b.PowerScheme } else { $Balanced }
    powercfg /setactive $target
    if ($LASTEXITCODE -ne 0) { powercfg /setactive $Balanced }
    if ($b.MyPlan) { powercfg /delete $b.MyPlan | Out-Null }
    Write-Host '   Қуат режимі қайтарылды'
    $ok++
} catch {
    Write-Host "   [!] Қуат режимі: $($_.Exception.Message)" -ForegroundColor Yellow
    $fail++
}

# services
foreach ($s in @($b.Services)) {
    if (-not $s) { continue }
    try {
        Set-Service -Name $s.Name -StartupType $s.StartType
        if ($s.StartType -eq 'Automatic') { Start-Service -Name $s.Name -ErrorAction SilentlyContinue }
        Write-Host "   Қызмет қайтарылды: $($s.Name) ($($s.StartType))"
        $ok++
    } catch {
        Write-Host "   [!] $($s.Name): $($_.Exception.Message)" -ForegroundColor Yellow
        $fail++
    }
}

# removed apps cannot be reinstalled automatically
$apps = @($b.RemovedApps | Where-Object { $_ })
if ($apps.Count -gt 0) {
    Write-Host ''
    Write-Host '   Өшірілген қолданбалар (керек болса Microsoft Store-дан қайта орнат):' -ForegroundColor Yellow
    foreach ($a in $apps) { Write-Host "     - $a" }
}

Move-Item -LiteralPath $BackupFile -Destination (Join-Path $BackupDir ('restored-{0:yyyyMMdd-HHmmss}.json' -f (Get-Date))) -Force

Write-Host ''
Write-Host '=============================================' -ForegroundColor Cyan
Write-Host ("   Дайын: {0} өтті, {1} өтпеді. Компьютерді ҚАЙТА ҚОС." -f $ok, $fail) -ForegroundColor Green
Write-Host '=============================================' -ForegroundColor Cyan
Read-Host 'Enter бас'
