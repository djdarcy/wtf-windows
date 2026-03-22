# Event Reference -- wtf-locked

All Windows events queried by wtf-locked's investigation engine.

## Primary Lock Events

### Security Log (requires audit policy)

| Event ID | Log | Provider | Meaning |
|----------|-----|----------|---------|
| 4800 | Security | Microsoft-Windows-Security-Auditing | Workstation was locked |
| 4801 | Security | Microsoft-Windows-Security-Auditing | Workstation was unlocked |
| 4802 | Security | Microsoft-Windows-Security-Auditing | Screen saver invoked |
| 4803 | Security | Microsoft-Windows-Security-Auditing | Screen saver dismissed |

**Audit policy required:**
```
auditpol /set /subcategory:"Other Logon/Logoff Events" /success:enable
```

Events 4800/4801 include `TargetUserSid`, `TargetUserName`, `TargetDomainName`, and `SessionId` in their EventData fields.

### Winlogon/Operational (always available -- no audit needed)

| Event ID | Notification Type | Meaning |
|----------|-------------------|---------|
| 811 | 7 | SESSION_LOCK -- session was locked |
| 811 | 8 | SESSION_UNLOCK -- session was unlocked |
| 811 | 4 | REMOTE_DISCONNECT -- RDP session disconnected (console effectively locked) |
| 811 | 5 | SESSION_LOGON -- user logged on to session |
| 811 | 9 | SESSION_REMOTE_CONTROL -- remote control of session |

**Note:** Multiple subscribers (TermSrv, Sens, SessionEnv) fire per event. The investigation script deduplicates by (timestamp, notification type) using only event ID 811 (begin notification).

**Winlogon notification types reference:**

| Type | Name | Description |
|------|------|-------------|
| 1 | CONSOLE_CONNECT | Console session connected |
| 2 | CONSOLE_DISCONNECT | Console session disconnected |
| 3 | REMOTE_CONNECT | Remote (RDP) session connected |
| 4 | REMOTE_DISCONNECT | Remote (RDP) session disconnected |
| 5 | SESSION_LOGON | User logged on to session |
| 6 | SESSION_LOGOFF | User logged off from session |
| 7 | SESSION_LOCK | Session was locked |
| 8 | SESSION_UNLOCK | Session was unlocked |
| 9 | SESSION_REMOTE_CONTROL | Session is being remotely controlled |

## Logon Events

### Security Log (for concurrent login detection)

| Event ID | Log | Meaning |
|----------|-----|---------|
| 4624 | Security | Successful logon |
| 4625 | Security | Failed logon (future: attempted access correlation) |

**Logon Type field in 4624 EventData:**

| Logon Type | Name | Description | Relevance |
|------------|------|-------------|-----------|
| 2 | Interactive | Console logon (keyboard) | Direct physical access |
| 3 | Network | Network logon (file share, etc.) | Not lock-relevant |
| 10 | RemoteInteractive | RDP logon | Key for REMOTE_TAKEOVER detection |
| 11 | CachedInteractive | Cached credentials logon | Domain controller offline |

**Key fields from 4624 EventData:**
- `TargetUserName` -- account that logged in
- `TargetDomainName` -- domain of the account
- `LogonType` -- how they authenticated
- `IpAddress` -- source IP (critical for RDP detection)
- `WorkstationName` -- source machine name
- `TargetUserSid` -- SID for cross-referencing with lock events

## RDP Session Events

### TerminalServices-LocalSessionManager/Operational (always available)

| Event ID | Meaning |
|----------|---------|
| 21 | Session logon (RDP user connected) |
| 23 | Session logoff (RDP user disconnected cleanly) |
| 24 | Session disconnect (RDP session dropped) |
| 25 | Session reconnect (RDP user reconnected) |

**UserData fields:**
- `User` -- domain\username of the RDP user
- `SessionID` -- terminal server session number
- `Address` -- source IP address of the RDP client

## Power Events

### System Log (always available)

| Event ID | Provider | Meaning |
|----------|----------|---------|
| 42 | Microsoft-Windows-Kernel-Power | System entering sleep |
| 107 | Microsoft-Windows-Kernel-Power | System resumed from sleep |
| 507 | Microsoft-Windows-Kernel-Power | Display timeout / power transition |

## Registry Settings

### Screen Saver

| Registry Path | Value | Meaning |
|---------------|-------|---------|
| `HKCU:\Control Panel\Desktop\ScreenSaveActive` | 1/0 | Screen saver enabled |
| `HKCU:\Control Panel\Desktop\ScreenSaverIsSecure` | 1/0 | Lock on resume |
| `HKCU:\Control Panel\Desktop\ScreenSaveTimeOut` | seconds | Idle timeout before screen saver |
| `HKCU:\Control Panel\Desktop\SCRNSAVE.EXE` | path | Screen saver executable |

### Inactivity Timeout

| Registry Path | Value | Meaning |
|---------------|-------|---------|
| `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\InactivityTimeoutSecs` | seconds | Machine inactivity lock timeout (0 = disabled) |

### Group Policy

| Registry Path | Value | Meaning |
|---------------|-------|---------|
| `HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\ScreenSaverGracePeriod` | seconds | GPO screen saver grace period |

### Dynamic Lock

| Registry Path | Value | Meaning |
|---------------|-------|---------|
| `HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon\EnableGoodbye` | 1/0 | Bluetooth Dynamic Lock enabled |

## PowerShell Queries

To manually query these events:

```powershell
# Lock/unlock events (requires audit policy)
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=@(4800,4801)} -MaxEvents 10

# Winlogon lock events (always available)
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Winlogon/Operational'; Id=811} -MaxEvents 20 |
    Where-Object { $_.Message -match 'notification event \((4|7|8)\)' }

# RDP session events
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TerminalServices-LocalSessionManager/Operational'; Id=@(21,23,24,25)} -MaxEvents 20

# Recent logons (interactive + RDP)
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624} -MaxEvents 20 |
    Where-Object { $_.Properties[8].Value -in 2,10,11 }

# Screen saver settings
Get-ItemProperty "HKCU:\Control Panel\Desktop" | Select-Object ScreenSave*, SCRNSAVE*
```
