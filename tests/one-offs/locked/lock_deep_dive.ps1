# Deep dive into screen lock at ~04:41:29
# Check all event sources in the 2 minutes BEFORE the lock

$lockTime = Get-Date "2026-02-15 04:41:29"
$before = $lockTime.AddMinutes(-5)
$after = $lockTime.AddMinutes(2)

Write-Host "============================================================"
Write-Host "  Screen Lock Deep Dive"
Write-Host "  Lock occurred at: $($lockTime.ToString('HH:mm:ss'))"
Write-Host "  Checking window: $($before.ToString('HH:mm:ss')) to $($after.ToString('HH:mm:ss'))"
Write-Host "============================================================"
Write-Host ""

# === 1. ALL Winlogon events in window (including lock event 7) ===
Write-Host "=== ALL Winlogon Events (lock=7, unlock=8) ==="
try {
    $events = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Winlogon/Operational'; StartTime=$before; EndTime=$after} -MaxEvents 50 -ErrorAction Stop
    foreach ($evt in $events) {
        # Extract notification type from message
        $notifType = ""
        if ($evt.Message -match 'notification event \((\d+)\)') {
            $typeNum = $Matches[1]
            $notifType = switch ($typeNum) {
                "1" { "(CONSOLE_CONNECT)" }
                "2" { "(CONSOLE_DISCONNECT)" }
                "3" { "(REMOTE_CONNECT)" }
                "4" { "(REMOTE_DISCONNECT)" }
                "5" { "(SESSION_LOGON)" }
                "6" { "(SESSION_LOGOFF)" }
                "7" { "(SESSION_LOCK)" }
                "8" { "(SESSION_UNLOCK)" }
                "9" { "(SESSION_REMOTE_CONTROL)" }
                default { "(type $typeNum)" }
            }
        }
        $subscriber = ""
        if ($evt.Message -match 'subscriber <(\w+)>') {
            $subscriber = $Matches[1]
        }
        $action = if ($evt.Id -eq 811) { "BEGIN" } elseif ($evt.Id -eq 812) { "END  " } else { "ID=$($evt.Id)" }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $action $subscriber $notifType"
    }
} catch {
    Write-Host "  $($_.Exception.Message)"
}
Write-Host ""

# === 2. Security Log: ALL events in the 1 min around lock ===
Write-Host "=== Security Log: Events around lock time ==="
try {
    $nearLock = $lockTime.AddSeconds(-30)
    $afterLock = $lockTime.AddSeconds(60)
    $secEvents = Get-WinEvent -FilterHashtable @{LogName='Security'; StartTime=$nearLock; EndTime=$afterLock} -MaxEvents 50 -ErrorAction Stop
    foreach ($evt in $secEvents) {
        $msgFirst = ($evt.Message -split "`n")[0]
        if ($msgFirst.Length -gt 120) { $msgFirst = $msgFirst.Substring(0, 120) + "..." }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] ID=$($evt.Id) $msgFirst"
    }
} catch {
    Write-Host "  $($_.Exception.Message)"
}
Write-Host ""

# === 3. System Log: ALL events in window ===
Write-Host "=== System Log: ALL events 2min before lock ==="
try {
    $sysEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$before; EndTime=$after} -MaxEvents 100 -ErrorAction Stop
    foreach ($evt in $sysEvents) {
        $msgTrunc = $evt.Message -replace "`r`n", " " -replace "`n", " "
        if ($msgTrunc.Length -gt 160) { $msgTrunc = $msgTrunc.Substring(0, 160) + "..." }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $($evt.ProviderName) ID=$($evt.Id) $msgTrunc"
    }
} catch {
    Write-Host "  $($_.Exception.Message)"
}
Write-Host ""

# === 4. Check power plan display/sleep timeouts ===
Write-Host "=== Power Plan: Display and Sleep Timeouts ==="
Write-Host "--- Current power scheme ---"
powercfg /getactivescheme
Write-Host ""
Write-Host "--- Display timeout (AC) ---"
powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE
Write-Host ""
Write-Host "--- Console lock display off timeout ---"
powercfg /query SCHEME_CURRENT SUB_NONE CONSOLELOCK
Write-Host ""
Write-Host "--- Sleep timeout (AC) ---"
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
Write-Host ""

# === 5. Check for screen saver with default timeout ===
Write-Host "=== Screensaver Registry (full dump) ==="
$desktopProps = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop" -ErrorAction SilentlyContinue
$relevantProps = $desktopProps.PSObject.Properties | Where-Object { $_.Name -match 'Screen|SCRN|Lock|Idle' }
foreach ($prop in $relevantProps) {
    Write-Host "  $($prop.Name) = '$($prop.Value)'"
}
Write-Host ""

# === 6. Check if any process called LockWorkStation ===
Write-Host "=== Event 4688: Process creations in 30s before lock ==="
try {
    $preLock = $lockTime.AddSeconds(-30)
    $procEvents = Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4688; StartTime=$preLock; EndTime=$lockTime} -MaxEvents 50 -ErrorAction Stop
    foreach ($evt in $procEvents) {
        $xml = [xml]$evt.ToXml()
        $newProc = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'NewProcessName' }).'#text'
        $parentProc = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'ParentProcessName' }).'#text'
        $cmdLine = ($xml.Event.EventData.Data | Where-Object { $_.Name -eq 'CommandLine' }).'#text'
        if ($cmdLine.Length -gt 120) { $cmdLine = $cmdLine.Substring(0, 120) + "..." }
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] $newProc"
        Write-Host "    Parent: $parentProc"
        if ($cmdLine) { Write-Host "    Cmd: $cmdLine" }
    }
} catch {
    Write-Host "  $($_.Exception.Message)"
}
Write-Host ""

# === 7. Remote Desktop / Terminal Services ===
Write-Host "=== Remote Desktop Connection Events ==="
try {
    $rdpEvents = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TerminalServices-LocalSessionManager/Operational'; StartTime=$before; EndTime=$after} -MaxEvents 20 -ErrorAction Stop
    foreach ($evt in $rdpEvents) {
        Write-Host "  [$($evt.TimeCreated.ToString('HH:mm:ss.fff'))] ID=$($evt.Id) $($evt.Message.Substring(0, [Math]::Min(200, $evt.Message.Length)))"
    }
} catch {
    Write-Host "  No RDP session events"
}
Write-Host ""

Write-Host "Done."
