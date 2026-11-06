<#
  Ping + FPS optimization for Windows 10/11.
  Every change is backed up to %ProgramData%\PingFpsTweak\backup.json
  and can be undone with Restore.bat.
#>
$ErrorActionPreference = 'Stop'

# --- run as Administrator (self-elevate) ---
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

$Host.UI.RawUI.WindowTitle = 'Ping + FPS optimization'

$BackupDir  = Join-Path $env:ProgramData 'PingFpsTweak'
$BackupFile = Join-Path $BackupDir 'backup.json'
$MyPlan     = '9f3c1a52-7e44-4b1d-8c2a-5d6e7f809a1b'   # our own copy of "Ultimate Performance"
$Ultimate   = 'e9a42b02-d5df-448d-aa00-03f14749eb61'
$HighPerf   = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
$MM         = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile'
$IfRoot     = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces'
$DoKey      = 'Registry::HKEY_USERS\S-1-5-20\Software\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Settings'

# Preinstalled promo apps only. Xbox / Game Bar / Store / Photos / Calculator are NOT touched.
$Bloat = @(
    'Microsoft.BingNews', 'Microsoft.BingWeather', 'Microsoft.GetHelp', 'Microsoft.Getstarted',
    'Microsoft.WindowsFeedbackHub', 'Microsoft.MicrosoftSolitaireCollection', 'Microsoft.MicrosoftOfficeHub',
    'Microsoft.WindowsMaps', 'Microsoft.ZuneVideo', 'Microsoft.People', 'Microsoft.MixedReality.Portal',
    'Microsoft.Microsoft3DViewer', 'Microsoft.3DBuilder', 'Microsoft.SkypeApp', 'Microsoft.Messaging',
    'Microsoft.OneConnect', 'Microsoft.549981C3F5F10', 'Microsoft.PowerAutomateDesktop',
    'Clipchamp.Clipchamp', 'MicrosoftCorporationII.MicrosoftFamily',
    'king.com.CandyCrushSaga', 'king.com.CandyCrushSodaSaga', 'king.com.BubbleWitch3Saga'
)

# Programs that eat bandwidth in the background (only reported, never killed).
$Hogs = @('steam', 'EpicGamesLauncher', 'qbittorrent', 'uTorrent', 'BitTorrent', 'OneDrive', 'Dropbox',
          'GoogleDriveFS', 'Battle.net', 'EADesktop', 'upc', 'Origin', 'MEGAsync', 'YandexDisk2')

# ---------------- backup ----------------
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$Backup = [pscustomobject]@{
    Created     = (Get-Date).ToString('s')
    PowerScheme = $null
    MyPlan      = $MyPlan
    Registry    = [System.Collections.ArrayList]::new()
    Services    = [System.Collections.ArrayList]::new()
    RemovedApps = [System.Collections.ArrayList]::new()
}
if (Test-Path -LiteralPath $BackupFile) {
    # Re-run: keep the ORIGINAL values from the first run.
    $old = Get-Content -LiteralPath $BackupFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $Backup.Created     = $old.Created
    $Backup.PowerScheme = $old.PowerScheme
    foreach ($e in @($old.Registry))    { if ($e) { [void]$Backup.Registry.Add($e) } }
    foreach ($e in @($old.Services))    { if ($e) { [void]$Backup.Services.Add($e) } }
    foreach ($e in @($old.RemovedApps)) { if ($e) { [void]$Backup.RemovedApps.Add($e) } }
}

function Save-Backup {
    $Backup | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $BackupFile -Encoding UTF8
}

function Get-RegState {
    param([string]$Path, [string]$Name)
    $state = [ordered]@{ Path = $Path; Name = $Name; Existed = $false; Kind = $null; Value = $null }
    if (Test-Path -LiteralPath $Path) {
        $key = Get-Item -LiteralPath $Path
        if ($key.GetValueNames() -contains $Name) {
            $state.Existed = $true
            $state.Kind    = $key.GetValueKind($Name).ToString()
            $state.Value   = $key.GetValue($Name, $null, 'DoNotExpandEnvironmentNames')
        }
    }
    [pscustomobject]$state
}

function Set-Reg {
    param([string]$Path, [string]$Name, [string]$Kind, $Value)
    $id = "$Path|$Name"
    if (-not ($Backup.Registry | Where-Object { "$($_.Path)|$($_.Name)" -eq $id })) {
        [void]$Backup.Registry.Add((Get-RegState $Path $Name))
        Save-Backup
    }
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -Path $Path -Force | Out-Null }
    New-ItemProperty -LiteralPath $Path -Name $Name -PropertyType $Kind -Value $Value -Force | Out-Null
}

function Get-DirBytes {
    param([string]$Dir)
    $s = (Get-ChildItem -LiteralPath $Dir -Recurse -Force -File -ErrorAction SilentlyContinue |
          Measure-Object -Property Length -Sum).Sum
    if ($s) { [double]$s } else { 0 }
}

function Test-Latency {
    param([string]$Target, [int]$Count = 20)
    $ping = New-Object System.Net.NetworkInformation.Ping
    $t = [System.Collections.Generic.List[double]]::new()
    $lost = 0
    for ($i = 0; $i -lt $Count; $i++) {
        try {
            $r = $ping.Send($Target, 1000)
            if ($r.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) { $t.Add([double]$r.RoundtripTime) }
            else { $lost++ }
        } catch { $lost++ }
        Start-Sleep -Milliseconds 150
    }
    if ($t.Count -eq 0) { Write-Host "   $Target : жауап жоқ" -ForegroundColor Yellow; return }
    $jit = 0.0
    for ($i = 1; $i -lt $t.Count; $i++) { $jit += [math]::Abs($t[$i] - $t[$i - 1]) }
    if ($t.Count -gt 1) { $jit = $jit / ($t.Count - 1) }
    $m = $t | Measure-Object -Average -Minimum -Maximum
    Write-Host ("   {0,-8} орташа {1,4:N0} ms | мин {2:N0} | макс {3:N0} | джиттер {4:N1} ms | жоғалту {5:N0}%" -f `
        $Target, $m.Average, $m.Minimum, $m.Maximum, $jit, (100 * $lost / $Count))
}

$script:Ok = 0
$script:Fail = 0
function Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host ''
    Write-Host ">> $Title" -ForegroundColor Cyan
    try {
        & $Action
        Write-Host '   [OK]' -ForegroundColor Green
        $script:Ok++
    } catch {
        Write-Host "   [!] Өтпеді: $($_.Exception.Message)" -ForegroundColor Yellow
        $script:Fail++
    }
}

# ---------------- start ----------------
Clear-Host
Write-Host '=============================================' -ForegroundColor Cyan
Write-Host '   ПИНГ + FPS ОПТИМИЗАЦИЯСЫ  (Windows 10/11)' -ForegroundColor Cyan
Write-Host '   Қайтару үшін: Restore.bat' -ForegroundColor Cyan
Write-Host '=============================================' -ForegroundColor Cyan

if ([Environment]::OSVersion.Version.Major -lt 10) {
    Write-Host 'Бұл скрипт тек Windows 10/11 үшін.' -ForegroundColor Red
    Read-Host 'Enter бас'
    exit
}

Step 'Қуат режимі -> максималды өнімділік (FPS)' {
    $cur = $null
    if (((powercfg /getactivescheme) -join ' ') -match '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}') { $cur = $Matches[0] }
    if (-not $Backup.PowerScheme -and $cur -and $cur -ne $MyPlan) { $Backup.PowerScheme = $cur; Save-Backup }
    if (((powercfg /list) -join ' ') -notmatch $MyPlan) {
        powercfg /duplicatescheme $Ultimate $MyPlan | Out-Null
    }
    powercfg /setactive $MyPlan
    if ($LASTEXITCODE -eq 0) {
        Write-Host '   Ultimate Performance қойылды'
    } else {
        powercfg /setactive $HighPerf
        if ($LASTEXITCODE -ne 0) { throw 'бұл жүйеде қуат режимін ауыстыру мүмкін емес' }
        Write-Host '   High Performance қойылды'
    }
    if (Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue) {
        Write-Host '   Ноутбук: ойнағанда зарядкаға қосулы болсын.' -ForegroundColor Yellow
    }
}

Step 'Game Mode қосу, фондық Xbox жазбасын (Game DVR) өшіру (FPS)' {
    Set-Reg 'HKCU:\Software\Microsoft\GameBar' 'AutoGameModeEnabled' 'DWord' 1
    Set-Reg 'HKCU:\Software\Microsoft\GameBar' 'AllowAutoGameMode' 'DWord' 1
    Set-Reg 'HKCU:\System\GameConfigStore' 'GameDVR_Enabled' 'DWord' 0
    Set-Reg 'HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR' 'AppCaptureEnabled' 'DWord' 0
}

Step 'Ойындарға CPU/GPU басымдығы (FPS)' {
    Set-Reg $MM 'SystemResponsiveness' 'DWord' 10
    Set-Reg "$MM\Tasks\Games" 'GPU Priority' 'DWord' 8
    Set-Reg "$MM\Tasks\Games" 'Priority' 'DWord' 6
    Set-Reg "$MM\Tasks\Games" 'Scheduling Category' 'String' 'High'
    Set-Reg "$MM\Tasks\Games" 'SFIO Priority' 'String' 'High'
}

Step 'Желі: throttling өшіру, Nagle өшіру, DNS кэш тазалау (пинг)' {
    Set-Reg $MM 'NetworkThrottlingIndex' 'DWord' (-1)   # -1 = 0xFFFFFFFF = throttling off
    $n = 0
    foreach ($a in @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' })) {
        $p = Join-Path $IfRoot $a.InterfaceGuid
        if (Test-Path -LiteralPath $p) {
            Set-Reg $p 'TcpAckFrequency' 'DWord' 1
            Set-Reg $p 'TCPNoDelay' 'DWord' 1
            $n++
        }
    }
    Write-Host "   Желі адаптерлері: $n"
    ipconfig /flushdns | Out-Null
}

Step 'Windows жаңартуларын басқа ПК-ларға таратуды өшіру (пинг)' {
    Set-Reg $DoKey 'DownloadMode' 'DWord' 0
}

Step 'Телеметрия қызметін (DiagTrack) өшіру' {
    $svc = Get-Service -Name 'DiagTrack' -ErrorAction SilentlyContinue
    if (-not $svc) { Write-Host '   Қызмет жоқ — өткізілді'; return }
    if (-not ($Backup.Services | Where-Object { $_.Name -eq 'DiagTrack' })) {
        [void]$Backup.Services.Add([pscustomobject]@{ Name = 'DiagTrack'; StartType = $svc.StartType.ToString() })
        Save-Backup
    }
    Stop-Service -Name 'DiagTrack' -Force -ErrorAction SilentlyContinue
    Set-Service -Name 'DiagTrack' -StartupType Disabled
}

Step 'Керексіз алдын ала орнатылған қолданбаларды өшіру' {
    $removed = 0
    foreach ($name in $Bloat) {
        foreach ($pkg in @(Get-AppxPackage -Name $name -ErrorAction SilentlyContinue)) {
            if (-not $pkg) { continue }
            try {
                Remove-AppxPackage -Package $pkg.PackageFullName -ErrorAction Stop
                if (-not ($Backup.RemovedApps -contains $pkg.Name)) { [void]$Backup.RemovedApps.Add($pkg.Name) }
                Write-Host "   - $($pkg.Name)"
                $removed++
            } catch {
                Write-Host "   ~ $($pkg.Name): өшпеді" -ForegroundColor DarkYellow
            }
        }
    }
    Save-Backup
    Write-Host "   Өшірілді: $removed"
}

Step 'Temp файлдарды тазалау' {
    $freed = 0.0
    foreach ($d in @($env:TEMP, (Join-Path $env:SystemRoot 'Temp'))) {
        if (-not $d -or -not (Test-Path -LiteralPath $d)) { continue }
        $before = Get-DirBytes $d
        try {
            Get-ChildItem -LiteralPath $d -Force -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        } catch { }
        $freed += [math]::Max(0.0, $before - (Get-DirBytes $d))
    }
    Write-Host ("   Босатылды: {0:N0} MB" -f ($freed / 1MB))
}

# ---------------- checks (read-only) ----------------
Write-Host ''
Write-Host '== ТЕКСЕРУ ==' -ForegroundColor Cyan

try {
    $up = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' })
    $wifi = @($up | Where-Object { $_.PhysicalMediaType -match '802\.11' -or $_.NdisPhysicalMedium -eq 9 })
    if ($wifi.Count -gt 0) {
        Write-Host '   Wi-Fi арқылы қосылғансың. Пингке ең көп әсер — LAN кабель. Мүмкін болса кабельмен қос.' -ForegroundColor Yellow
    } elseif ($up.Count -gt 0) {
        Write-Host '   Кабель (LAN) арқылы қосылғансың — жақсы.' -ForegroundColor Green
    }
} catch { }

$running = @(Get-Process -Name $Hogs -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName -Unique)
if ($running.Count -gt 0) {
    Write-Host '   Интернетті фонда жеуі мүмкін — ойын кезінде жап:' -ForegroundColor Yellow
    foreach ($p in $running) { Write-Host "     - $p" }
}

$startup = @(Get-CimInstance -ClassName Win32_StartupCommand -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty Name -Unique)
if ($startup.Count -gt 0) {
    Write-Host "   Компьютермен бірге қосылатын бағдарламалар ($($startup.Count)):"
    foreach ($s in $startup) { Write-Host "     - $s" }
    Write-Host '   Керек еместерін өшір: Ctrl+Shift+Esc -> Автозагрузка (Startup apps) -> Disable' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '   Пинг тесті (интернетке дейін, 20 рет):'
Test-Latency '1.1.1.1'
Test-Latency '8.8.8.8'
Write-Host '   (Ойын серверіне пинг — сервердің қашықтығына байланысты; ойында ең жақын серверді таңда.)' -ForegroundColor DarkGray

# ---------------- done ----------------
Write-Host ''
Write-Host '=============================================' -ForegroundColor Cyan
Write-Host ("   Дайын: {0} қадам өтті, {1} өтпеді." -f $script:Ok, $script:Fail) -ForegroundColor Green
Write-Host '   Толық күшіне енуі үшін компьютерді ҚАЙТА ҚОС.' -ForegroundColor Green
Write-Host "   Резерв: $BackupFile"
Write-Host '=============================================' -ForegroundColor Cyan
$ans = Read-Host 'Қазір қайта қосайын ба? (y = иә, Enter = кейін)'
if ($ans -match '^\s*(y|yes|и|иә|д|да)\s*$') {
    Write-Host 'Ашық файлдарыңды сақта — 15 секундтан кейін қайта қосылады.' -ForegroundColor Yellow
    shutdown.exe /r /t 15
}
