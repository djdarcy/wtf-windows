# investigate_locks.ps1 - Collect lock/unlock events and related session data
#
# Queries MULTIPLE event sources to build the lock picture:
#   1. Winlogon/Operational (always available - lock=7, unlock=8)
#   2. Security log 4800/4801 (if audit policy enabled - more detail)
#   3. Security log 4802/4803 (screensaver events)
#   4. Security log 4624 (logon events for concurrent login detection)
#   5. TerminalServices session events (RDP - always available)
#   6. System log power events (sleep/wake - always available)
#   7. Registry settings (screensaver, inactivity, GPO)
#
# The tool ALWAYS returns useful data even without audit policies.
# Winlogon/Operational is the primary fallback source.
#
# Output: JSON to stdout (consumed by Python via run_ps1)

param(
    [int]$Hours = 720,
    [switch]$StrictLookback
)

$ErrorActionPreference = "SilentlyContinue"
$now = Get-Date
$After = $now.AddHours(-$Hours)

# Lock-anchored lookback: if not strict, find the most recent lock event
# and extend the window to cover it (like wtf-restarted's boot-anchored lookback).
$LookbackExtended = $false
$ActualHours = $Hours

if (-not $StrictLookback) {
    # Quick scan: find the most recent Winlogon lock event (any age)
    $RecentLock = $null
    try {
        $AllWinlogon = Get-WinEvent -FilterHashtable @{
            LogName = 'Microsoft-Windows-Winlogon/Operational'
        } -MaxEvents 500 -ErrorAction SilentlyContinue

        foreach ($evt in $AllWinlogon) {
            if ($evt.Message -match 'notification event \(7\)') {
                $RecentLock = $evt
                break
            }
        }
    } catch { }

    # Also check Security 4800 if available
    if (-not $RecentLock) {
        try {
            $RecentLock = Get-WinEvent -FilterHashtable @{
                LogName = 'Security'
                Id = 4800
            } -MaxEvents 1 -ErrorAction SilentlyContinue
        } catch { }
    }

    # If the most recent lock is older than our window, extend
    if ($RecentLock -and $RecentLock.TimeCreated -lt $After) {
        $After = $RecentLock.TimeCreated.AddMinutes(-5)
        $LookbackExtended = $true
        $ActualHours = [Math]::Round(($now - $After).TotalHours, 1)
    }
}

# --- Audit policy check ---
$AuditEnabled = $false
try {
    $AuditResult = auditpol /get /subcategory:"Other Logon/Logoff Events" 2>$null
    if ($AuditResult -match "Success") {
        $AuditEnabled = $true
    }
} catch { }

# =====================================================================
# SOURCE 1: Winlogon/Operational (ALWAYS AVAILABLE - primary fallback)
# Events 811/812 with notification types 7 (lock) and 8 (unlock)
# =====================================================================
$WinlogonLocks = @()
$WinlogonUnlocks = @()
try {
    $WinlogonEvents = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-Winlogon/Operational'
        StartTime = $After
    } -MaxEvents 500 -ErrorAction SilentlyContinue

    foreach ($evt in $WinlogonEvents) {
        $notifType = $null
        if ($evt.Message -match 'notification event \((\d+)\)') {
            $notifType = [int]$Matches[1]
        }
        $subscriber = ""
        if ($evt.Message -match 'subscriber <(\w+)>') {
            $subscriber = $Matches[1]
        }

        if ($notifType -eq 7) {
            # SESSION_LOCK
            $WinlogonLocks += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
                source = "winlogon"
                notification_type = 7
                subscriber = $subscriber
                message = ($evt.Message -replace "`r`n", " " -replace "`n", " ").Substring(0, [Math]::Min(200, $evt.Message.Length))
            }
        }
        elseif ($notifType -eq 8) {
            # SESSION_UNLOCK
            $WinlogonUnlocks += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
                source = "winlogon"
                notification_type = 8
                subscriber = $subscriber
            }
        }
    }
} catch { }

# =====================================================================
# SOURCE 2: Security Log lock/unlock (if audit enabled - richer data)
# =====================================================================
$SecurityLocks = @()
$SecurityUnlocks = @()
if ($AuditEnabled) {
    try {
        $Raw4800 = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id = 4800
            StartTime = $After
        } -ErrorAction SilentlyContinue

        foreach ($evt in $Raw4800) {
            $xml = [xml]$evt.ToXml()
            $eventData = @{}
            foreach ($d in $xml.Event.EventData.Data) {
                $eventData[$d.Name] = $d.'#text'
            }
            $SecurityLocks += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
                source = "security"
                session_id = [int]($eventData["SessionId"])
                user_sid = $eventData["TargetUserSid"]
                user_name = $eventData["TargetUserName"]
                domain = $eventData["TargetDomainName"]
                message = ($evt.Message -split "`n")[0]
            }
        }
    } catch { }

    try {
        $Raw4801 = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id = 4801
            StartTime = $After
        } -ErrorAction SilentlyContinue

        foreach ($evt in $Raw4801) {
            $xml = [xml]$evt.ToXml()
            $eventData = @{}
            foreach ($d in $xml.Event.EventData.Data) {
                $eventData[$d.Name] = $d.'#text'
            }
            $SecurityUnlocks += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
                source = "security"
                session_id = [int]($eventData["SessionId"])
                user_sid = $eventData["TargetUserSid"]
                user_name = $eventData["TargetUserName"]
            }
        }
    } catch { }
}

# Merge: prefer Security events (richer), fall back to Winlogon
$LockEvents = if ($SecurityLocks.Count -gt 0) { $SecurityLocks } else { $WinlogonLocks }
$UnlockEvents = if ($SecurityUnlocks.Count -gt 0) { $SecurityUnlocks } else { $WinlogonUnlocks }

# =====================================================================
# SOURCE 3: Screen saver events (4802/4803 - if audit enabled)
# =====================================================================
$ScreensaverEvents = @()
if ($AuditEnabled) {
    try {
        $RawSS = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id = 4802, 4803
            StartTime = $After
        } -ErrorAction SilentlyContinue

        foreach ($evt in $RawSS) {
            $ScreensaverEvents += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
            }
        }
    } catch { }
}

# =====================================================================
# SOURCE 4: Logon events (4624) for concurrent login detection
# =====================================================================
$LoginEvents = @()
try {
    $Raw4624 = Get-WinEvent -FilterHashtable @{
        LogName = 'Security'
        Id = 4624
        StartTime = $After
    } -MaxEvents 200 -ErrorAction SilentlyContinue

    foreach ($evt in $Raw4624) {
        $xml = [xml]$evt.ToXml()
        $eventData = @{}
        foreach ($d in $xml.Event.EventData.Data) {
            $eventData[$d.Name] = $d.'#text'
        }
        $logonType = [int]($eventData["LogonType"])
        # Only include interactive (2), RDP (10), cached (11) logons
        if ($logonType -in 2, 10, 11) {
            $LoginEvents += @{
                time = $evt.TimeCreated.ToString("o")
                event_id = $evt.Id
                user = $eventData["TargetUserName"]
                domain = $eventData["TargetDomainName"]
                logon_type = $logonType
                source_ip = $eventData["IpAddress"]
                source_hostname = $eventData["WorkstationName"]
                user_sid = $eventData["TargetUserSid"]
            }
        }
    }
} catch { }

# =====================================================================
# SOURCE 5: RDP session events (ALWAYS AVAILABLE)
# =====================================================================
$RdpEvents = @()
try {
    $RawRDP = Get-WinEvent -FilterHashtable @{
        LogName = 'Microsoft-Windows-TerminalServices-LocalSessionManager/Operational'
        Id = 21, 23, 24, 25
        StartTime = $After
    } -MaxEvents 100 -ErrorAction SilentlyContinue

    foreach ($evt in $RawRDP) {
        $xml = [xml]$evt.ToXml()
        $userData = @{}
        if ($xml.Event.UserData -and $xml.Event.UserData.EventXML) {
            foreach ($d in $xml.Event.UserData.EventXML.ChildNodes) {
                $userData[$d.Name] = $d.InnerText
            }
        }
        $RdpEvents += @{
            time = $evt.TimeCreated.ToString("o")
            event_id = $evt.Id
            event_type = switch ($evt.Id) {
                21 { "SESSION_LOGON" }
                23 { "SESSION_LOGOFF" }
                24 { "SESSION_DISCONNECT" }
                25 { "SESSION_RECONNECT" }
            }
            user = $userData["User"]
            session_id = $userData["SessionID"]
            source_ip = $userData["Address"]
            message = ($evt.Message -replace "`r`n", " " -replace "`n", " ")
        }
    }
} catch { }

# =====================================================================
# SOURCE 6: Power events - sleep/wake (ALWAYS AVAILABLE)
# =====================================================================
$PowerEvents = @()
try {
    $RawPower = Get-WinEvent -FilterHashtable @{
        LogName = 'System'
        ProviderName = 'Microsoft-Windows-Kernel-Power'
        Id = 42, 107, 507
        StartTime = $After
    } -MaxEvents 50 -ErrorAction SilentlyContinue

    foreach ($evt in $RawPower) {
        $PowerEvents += @{
            time = $evt.TimeCreated.ToString("o")
            event_id = $evt.Id
            message = ($evt.Message -split "`n")[0]
        }
    }
} catch { }

# =====================================================================
# SOURCE 7: Registry and GPO settings
# =====================================================================

# Screen saver settings
$SSConfig = @{
    ScreenSaveActive = "0"
    ScreenSaverIsSecure = "0"
    ScreenSaveTimeOut = "0"
    ScreenSaverExe = ""
}
try {
    $desktop = Get-ItemProperty "HKCU:\Control Panel\Desktop" -ErrorAction SilentlyContinue
    if ($desktop.ScreenSaveActive) { $SSConfig.ScreenSaveActive = $desktop.ScreenSaveActive }
    if ($desktop.ScreenSaverIsSecure) { $SSConfig.ScreenSaverIsSecure = $desktop.ScreenSaverIsSecure }
    if ($desktop.ScreenSaveTimeOut) { $SSConfig.ScreenSaveTimeOut = $desktop.ScreenSaveTimeOut }
    if ($desktop.'SCRNSAVE.EXE') { $SSConfig.ScreenSaverExe = $desktop.'SCRNSAVE.EXE' }
} catch { }

# Dynamic Lock (Bluetooth)
$DynamicLockEnabled = $false
try {
    $dynLock = Get-ItemProperty "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "EnableGoodbye" -ErrorAction SilentlyContinue
    if ($dynLock.EnableGoodbye -eq 1) { $DynamicLockEnabled = $true }
} catch { }

# Inactivity timeout
$InactivityTimeout = 0
try {
    $Val = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "InactivityTimeoutSecs" -ErrorAction SilentlyContinue).InactivityTimeoutSecs
    if ($Val) { $InactivityTimeout = [int]$Val }
} catch { }

# GPO machine inactivity limit
$GPOLimit = 0
try {
    $Val = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "ScreenSaverGracePeriod" -ErrorAction SilentlyContinue).ScreenSaverGracePeriod
    if ($Val) { $GPOLimit = [int]$Val }
    $Val2 = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "InactivityTimeoutSecs" -ErrorAction SilentlyContinue).InactivityTimeoutSecs
    if ($Val2 -and [int]$Val2 -gt $GPOLimit) { $GPOLimit = [int]$Val2 }
} catch { }

# Build SID to username mapping
$SidToUser = @{}
foreach ($evt in $SecurityLocks) {
    if ($evt.user_sid -and $evt.user_name) {
        $SidToUser[$evt.user_sid] = $evt.user_name
    }
}
foreach ($evt in $LoginEvents) {
    if ($evt.user_sid -and $evt.user) {
        $SidToUser[$evt.user_sid] = $evt.user
    }
}

# =====================================================================
# OUTPUT
# =====================================================================
$Output = @{
    audit_policy_enabled = $AuditEnabled
    lock_events = $LockEvents
    unlock_events = $UnlockEvents
    winlogon_lock_count = $WinlogonLocks.Count
    security_lock_count = $SecurityLocks.Count
    screensaver_events = $ScreensaverEvents
    login_events = $LoginEvents
    rdp_events = $RdpEvents
    power_events = $PowerEvents
    screensaver_config = $SSConfig
    dynamic_lock_enabled = $DynamicLockEnabled
    inactivity_timeout_secs = $InactivityTimeout
    gpo_inactivity_limit = $GPOLimit
    sid_to_user = $SidToUser
    lookback_hours = $Hours
    lookback_extended = $LookbackExtended
    lookback_actual_hours = $ActualHours
    strict_lookback = [bool]$StrictLookback
    query_time = (Get-Date).ToString("o")
    computer_name = $env:COMPUTERNAME
}

$Output | ConvertTo-Json -Depth 4
