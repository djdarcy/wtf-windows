# Investigate unexpected screen lock events
# Checks multiple event logs for lock triggers, power events, and screensaver activity

param(
    [int]$Minutes = 30
)

$since = (Get-Date).AddMinutes(-$Minutes)
Write-Host "============================================================"
Write-Host "  Screen Lock Investigation"
Write-Host "  Checking last $Minutes minutes from $($since.ToString('HH:mm:ss'))"
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "============================================================"
Write-Host ""

# === 1. Security Log: Lock/Unlock Events ===
Write-Host "=== Security Log: Workstation Lock (4800) / Unlock (4801) ==="
try {
    $lockEvents = Get-WinEvent -FilterHashtable @{LogName='Security'; Id=@(4800,4801); StartTime=$since} -MaxEvents 20 -ErrorAction Stop
    foreach ($evt in $lockEvents) {
        $xml = [xml]$evt.ToXml()
        $user = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'TargetUserName' }).'#text'
        $action = if ($evt.Id -eq 4800) { "LOCKED" } else { "UNLOCKED" }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $action by user: $user"
    }
} catch {
    Write-Host "  No lock/unlock events found (4800/4801 may not be audited)"
    Write-Host "  Error: $($_.Exception.Message)"
}
Write-Host ""

# === 2. Winlogon Events ===
Write-Host "=== Winlogon/Operational Events ==="
try {
    $winlogonEvents = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Winlogon/Operational'; StartTime=$since} -MaxEvents 20 -ErrorAction Stop
    foreach ($evt in $winlogonEvents) {
        $msgTrunc = $evt.Message
        if ($msgTrunc.Length -gt 200) { $msgTrunc = $msgTrunc.Substring(0, 200) + "..." }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] ID=$($evt.Id) $msgTrunc"
    }
} catch {
    Write-Host "  No Winlogon events found or log not available"
}
Write-Host ""

# === 3. System Log: Power and Display Events ===
Write-Host "=== System Log: Power/Display/Sleep Events ==="
try {
    $sysEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$since} -MaxEvents 200 -ErrorAction Stop
    $filtered = $sysEvents | Where-Object {
        $_.ProviderName -match 'Power|Kernel-Power|Display|ACPI|UserModePowerService' -or
        $_.Id -in @(1, 12, 13, 42, 107, 131, 187, 506, 507, 566) -or
        $_.Message -match 'lock|sleep|suspend|standby|hibernate|display|screen|idle|power|resume'
    }
    if ($filtered) {
        foreach ($evt in $filtered) {
            $msgTrunc = $evt.Message -replace "`r`n", " " -replace "`n", " "
            if ($msgTrunc.Length -gt 200) { $msgTrunc = $msgTrunc.Substring(0, 200) + "..." }
            Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $($evt.ProviderName) ID=$($evt.Id)"
            Write-Host "    $msgTrunc"
        }
    } else {
        Write-Host "  No power/display events found"
    }
} catch {
    Write-Host "  Error querying System log: $($_.Exception.Message)"
}
Write-Host ""

# === 4. Task Scheduler Events (scheduled lock?) ===
Write-Host "=== Task Scheduler: Recent Task Runs ==="
try {
    $taskEvents = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational'; Id=@(100,102,200,201); StartTime=$since} -MaxEvents 30 -ErrorAction Stop
    foreach ($evt in $taskEvents) {
        $xml = [xml]$evt.ToXml()
        $taskName = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'TaskName' }).'#text'
        $action = switch ($evt.Id) {
            100 { "STARTED" }
            102 { "COMPLETED" }
            200 { "ACTION_STARTED" }
            201 { "ACTION_COMPLETED" }
        }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $action : $taskName"
    }
} catch {
    Write-Host "  No recent task scheduler events"
}
Write-Host ""

# === 5. Screen Saver / Dynamic Lock / Remote Desktop ===
Write-Host "=== Screen Lock Settings ==="

# Check screen saver
$ssTimeout = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name ScreenSaveTimeOut -ErrorAction SilentlyContinue
$ssActive = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name ScreenSaveActive -ErrorAction SilentlyContinue
$ssSecure = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name ScreenSaverIsSecure -ErrorAction SilentlyContinue
$ssExe = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name SCRNSAVE.EXE -ErrorAction SilentlyContinue

Write-Host "  Screen Saver Active: $($ssActive.ScreenSaveActive) (1=enabled)"
Write-Host "  Screen Saver Timeout: $($ssTimeout.ScreenSaveTimeOut) seconds"
Write-Host "  Screen Saver Secure: $($ssSecure.ScreenSaverIsSecure) (1=requires password)"
Write-Host "  Screen Saver EXE: $($ssExe.'SCRNSAVE.EXE')"
Write-Host ""

# Check Dynamic Lock
$dynLock = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name EnableGoodbye -ErrorAction SilentlyContinue
Write-Host "  Dynamic Lock (Bluetooth): $(if ($dynLock.EnableGoodbye -eq 1) { 'ENABLED' } else { 'Disabled/Not set' })"
Write-Host ""

# Check power plan lock timeout
Write-Host "  Power Plan Lock Settings:"
$powerCfg = powercfg /query SCHEME_CURRENT SUB_NONE CONSOLELOCK 2>&1
$powerCfg | ForEach-Object { Write-Host "    $_" }
Write-Host ""

# === 6. Group Policy Lock Settings ===
Write-Host "=== Group Policy / InactivityTimeoutSecs ==="
$inactivity = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name InactivityTimeoutSecs -ErrorAction SilentlyContinue
if ($inactivity) {
    Write-Host "  InactivityTimeoutSecs: $($inactivity.InactivityTimeoutSecs) seconds"
} else {
    Write-Host "  InactivityTimeoutSecs: Not configured"
}

$lockPolicy = Get-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" -ErrorAction SilentlyContinue
if ($lockPolicy) {
    Write-Host "  Lock screen policy: $($lockPolicy | Format-List | Out-String)"
} else {
    Write-Host "  No lock screen group policies found"
}
Write-Host ""

# === 7. Recent Application Events (crash/error that could trigger lock) ===
Write-Host "=== Application Log: Errors/Warnings (last $Minutes min) ==="
try {
    $appEvents = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=@(1,2,3); StartTime=$since} -MaxEvents 15 -ErrorAction Stop
    foreach ($evt in $appEvents) {
        $msgTrunc = $evt.Message -replace "`r`n", " " -replace "`n", " "
        if ($msgTrunc.Length -gt 150) { $msgTrunc = $msgTrunc.Substring(0, 150) + "..." }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $($evt.ProviderName) (L$($evt.Level)) : $msgTrunc"
    }
} catch {
    Write-Host "  No application errors/warnings"
}
Write-Host ""

# === 8. Process Creation: Was LockApp or screensaver launched? ===
Write-Host "=== Event 4688: Lock-Related Process Creations ==="
try {
    $procEvents = Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4688; StartTime=$since} -MaxEvents 5000 -ErrorAction Stop
    $lockRelated = @()
    foreach ($evt in $procEvents) {
        $xml = [xml]$evt.ToXml()
        $newProc = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'NewProcessName' }).'#text'
        $parentProc = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'ParentProcessName' }).'#text'
        $cmdLine = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'CommandLine' }).'#text'
        if ($newProc -match 'LockApp|LogonUI|scrnsave|rundll32.*user32.*LockWorkStation|tsdiscon') {
            $lockRelated += [PSCustomObject]@{
                Time = $evt.TimeCreated.ToString('HH:mm:ss.fff')
                Process = $newProc
                Parent = $parentProc
                CmdLine = if ($cmdLine.Length -gt 120) { $cmdLine.Substring(0, 120) + "..." } else { $cmdLine }
            }
        }
    }
    if ($lockRelated.Count -gt 0) {
        $lockRelated | Format-Table -AutoSize -Wrap
    } else {
        Write-Host "  No LockApp/LogonUI/screensaver process creations found"
    }
} catch {
    Write-Host "  Error querying 4688: $($_.Exception.Message)"
}
Write-Host ""

Write-Host "============================================================"
Write-Host "  Investigation complete"
Write-Host "============================================================"
