"""Lock verdict classification and session modeling.

Verdicts are ordered by threat level (highest first):
  REMOTE_TAKEOVER     - Unknown user/IP connected and displaced console
  UNAUTHORIZED_LOGIN  - Different user account logged in
  SOFTWARE_LOCK       - A process called LockWorkStation()
  RDP_SELF_RECONNECT  - Own account reconnected from another machine
  SCREENSAVER_LOCK    - Screen saver triggered with lock-on-resume
  INACTIVITY_LOCK     - Inactivity timeout elapsed
  GROUP_POLICY_LOCK   - GPO-enforced lock
  SLEEP_RESUME_LOCK   - Machine slept, login required on wake
  MANUAL_LOCK         - User pressed Win+L (intentional)
  UNKNOWN_LOCK        - No automated trigger detected
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class ConcurrentLogin:
    """Details of a login that may have caused or accompanied a lock."""
    user: str
    domain: str
    source_ip: Optional[str]
    source_hostname: Optional[str]
    logon_type: int              # 2=Interactive, 3=Network, 10=RDP, 11=CachedInteractive
    logon_type_name: str
    timestamp: datetime
    event_id: int                # 4624 (success) or 4625 (failed)


@dataclass
class LockSession:
    """A lock/unlock pair with verdict and evidence."""
    locked_at: datetime
    unlocked_at: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    lock_cause: str = "UNKNOWN_LOCK"
    confidence: str = "low"       # "high", "medium", "low"
    evidence: List[str] = field(default_factory=list)
    concurrent_login: Optional[ConcurrentLogin] = None
    session_id: Optional[int] = None
    user_sid: Optional[str] = None


# Verdict threat levels (lower number = higher threat)
VERDICT_THREAT_LEVEL = {
    "REMOTE_TAKEOVER": 1,
    "UNAUTHORIZED_LOGIN": 2,
    "SOFTWARE_LOCK": 3,
    "RDP_SELF_RECONNECT": 4,
    "SCREENSAVER_LOCK": 5,
    "INACTIVITY_LOCK": 6,
    "GROUP_POLICY_LOCK": 7,
    "SLEEP_RESUME_LOCK": 8,
    "MANUAL_LOCK": 9,
    "UNKNOWN_LOCK": 10,
}


def pair_events(lock_events, unlock_events):
    """Pair lock (4800) and unlock (4801) events into sessions.

    Handles:
    - Normal pairs: lock followed by unlock
    - Unpaired locks: lock with no subsequent unlock (still locked or log trimmed)
    - Multiple consecutive locks: each gets its own session

    Returns list of (lock_event, unlock_event_or_None) tuples, sorted by time.
    """
    locks = sorted(lock_events, key=lambda e: e["time"])
    unlocks = sorted(unlock_events, key=lambda e: e["time"])

    pairs = []
    unlock_idx = 0

    for lock in locks:
        lock_time = _parse_time(lock["time"])

        # Find the next unlock that comes after this lock
        matched_unlock = None
        while unlock_idx < len(unlocks):
            unlock_time = _parse_time(unlocks[unlock_idx]["time"])
            if unlock_time > lock_time:
                matched_unlock = unlocks[unlock_idx]
                unlock_idx += 1
                break
            unlock_idx += 1

        pairs.append((lock, matched_unlock))

    return pairs


def classify_lock(lock_event, data):
    """Classify a lock event into a verdict with evidence.

    Uses ordered rules checked by threat level (highest first).
    The first matching rule wins.

    Args:
        lock_event: The 4800 event dict
        data: Full investigation data from investigate_locks.ps1

    Returns:
        (verdict, evidence_list, confidence, concurrent_login_or_None)
    """
    lock_time = _parse_time(lock_event["time"])
    lock_sid = lock_event.get("user_sid", "")
    lock_type = lock_event.get("lock_type", "")

    # --- Rule 0: RDP disconnect from Winlogon (always detected, no audit needed) ---
    if lock_type == "RDP_DISCONNECT":
        # Check if there's a concurrent RDP login that displaced us
        login = _find_concurrent_login(lock_time, data, window_secs=60)
        rdp_events = data.get("rdp_events", [])
        rdp_detail = _find_rdp_event(lock_time, rdp_events, window_secs=30)

        if login and login.logon_type == 10:
            if login.user.upper() != _current_user(lock_sid, data):
                return (
                    "REMOTE_TAKEOVER",
                    [
                        f"RDP session disconnected (Winlogon type 4)",
                        f"Different user connected: {login.domain}\\{login.user}",
                        f"Source: {login.source_ip or 'unknown'}"
                        + (f" ({login.source_hostname})" if login.source_hostname else ""),
                    ],
                    "high",
                    login,
                )
            else:
                source = ""
                if rdp_detail and rdp_detail.get("source_ip"):
                    source = f" from {rdp_detail['source_ip']}"
                return (
                    "RDP_SELF_RECONNECT",
                    [
                        f"RDP session disconnect/reconnect{source}",
                        "Own account reconnected from another machine",
                    ],
                    "medium",
                    login,
                )
        else:
            # RDP disconnect without a matching login event
            source = ""
            if rdp_detail and rdp_detail.get("source_ip"):
                source = f" from {rdp_detail['source_ip']}"
            return (
                "RDP_SELF_RECONNECT",
                [
                    f"RDP session disconnected{source}",
                    "Console session was displaced by RDP activity",
                ],
                "medium",
                None,
            )

    # --- Rule 1: Remote takeover (unknown user via RDP) ---
    login = _find_concurrent_login(lock_time, data, window_secs=60)
    if login and login.logon_type == 10:  # RDP
        if login.user.upper() != _current_user(lock_sid, data):
            return (
                "REMOTE_TAKEOVER",
                [
                    f"RDP login by {login.domain}\\{login.user}",
                    f"Source: {login.source_ip or 'unknown'}"
                    + (f" ({login.source_hostname})" if login.source_hostname else ""),
                    "Console session was displaced by remote connection",
                ],
                "high",
                login,
            )

    # --- Rule 2: Unauthorized login (different user, any method) ---
    if login and login.event_id == 4624:
        login_user = login.user.upper()
        lock_user = _current_user(lock_sid, data)
        if login_user and lock_user and login_user != lock_user:
            return (
                "UNAUTHORIZED_LOGIN",
                [
                    f"Login by {login.domain}\\{login.user} (type: {login.logon_type_name})",
                    f"Displaced session of different user",
                ],
                "high",
                login,
            )

    # --- Rule 3: RDP self-reconnect (own account from another machine) ---
    if login and login.logon_type == 10:
        return (
            "RDP_SELF_RECONNECT",
            [
                f"RDP reconnect from {login.source_ip or 'unknown'}"
                + (f" ({login.source_hostname})" if login.source_hostname else ""),
                "Own account connected from another machine",
            ],
            "medium",
            login,
        )

    # --- Rule 4: Screen saver lock ---
    if _screensaver_preceded(lock_time, data):
        ss_config = data.get("screensaver_config", {})
        if ss_config.get("ScreenSaverIsSecure") == "1":
            timeout = ss_config.get("ScreenSaveTimeOut", "?")
            return (
                "SCREENSAVER_LOCK",
                [
                    "Screen saver event (4802) preceded lock",
                    f"Lock-on-resume enabled, timeout: {timeout}s",
                ],
                "high",
                None,
            )

    # --- Rule 5: Inactivity timeout ---
    inactivity = data.get("inactivity_timeout_secs", 0)
    if inactivity > 0:
        return (
            "INACTIVITY_LOCK",
            [f"Machine inactivity timeout: {inactivity}s ({inactivity // 60}min)"],
            "medium",
            None,
        )

    # --- Rule 6: Group policy lock ---
    gpo_limit = data.get("gpo_inactivity_limit", 0)
    if gpo_limit > 0:
        return (
            "GROUP_POLICY_LOCK",
            [f"GPO machine inactivity limit: {gpo_limit}s ({gpo_limit // 60}min)"],
            "medium",
            None,
        )

    # --- Rule 7: Sleep/wake resume ---
    if _sleep_preceded(lock_time, data):
        return (
            "SLEEP_RESUME_LOCK",
            ["Machine resumed from sleep/hibernate"],
            "medium",
            None,
        )

    # --- Default: unknown cause ---
    return (
        "UNKNOWN_LOCK",
        ["No automated lock trigger detected -- may be manual (Win+L) or unrecognized cause"],
        "low",
        None,
    )


def build_sessions(lock_events, unlock_events, data):
    """Build a list of LockSession objects from raw event data.

    Pairs events, classifies each lock, and attaches concurrent login info.
    Returns sessions sorted most-recent-first.
    """
    pairs = pair_events(lock_events, unlock_events)
    sessions = []

    for lock_evt, unlock_evt in pairs:
        lock_time = _parse_time(lock_evt["time"])
        unlock_time = _parse_time(unlock_evt["time"]) if unlock_evt else None

        duration = None
        if unlock_time:
            delta = unlock_time - lock_time
            duration = delta.total_seconds() / 60.0

        verdict, evidence, confidence, concurrent = classify_lock(lock_evt, data)

        session = LockSession(
            locked_at=lock_time,
            unlocked_at=unlock_time,
            duration_minutes=round(duration, 1) if duration is not None else None,
            lock_cause=verdict,
            confidence=confidence,
            evidence=evidence,
            concurrent_login=concurrent,
            session_id=lock_evt.get("session_id"),
            user_sid=lock_evt.get("user_sid"),
        )
        sessions.append(session)

    # Most recent first
    sessions.sort(key=lambda s: s.locked_at, reverse=True)
    return sessions


# --- Helper functions ---

def _parse_time(time_str):
    """Parse ISO 8601 timestamp from PowerShell."""
    if not time_str:
        return datetime.min
    # Handle various ISO formats PowerShell might produce
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(time_str.rstrip("Z"), fmt.rstrip("%z"))
        except ValueError:
            continue
    # Fallback: try removing timezone suffix
    try:
        clean = time_str.split("+")[0].split("-04")[0].split("-05")[0].rstrip("Z")
        return datetime.fromisoformat(clean)
    except (ValueError, AttributeError):
        return datetime.min


def _find_concurrent_login(lock_time, data, window_secs=60):
    """Find a login event within window_secs of the lock time."""
    logins = data.get("login_events", [])
    window = timedelta(seconds=window_secs)

    for evt in logins:
        evt_time = _parse_time(evt.get("time", ""))
        if abs(evt_time - lock_time) <= window:
            logon_type = evt.get("logon_type", 0)
            return ConcurrentLogin(
                user=evt.get("user", ""),
                domain=evt.get("domain", ""),
                source_ip=evt.get("source_ip"),
                source_hostname=evt.get("source_hostname"),
                logon_type=logon_type,
                logon_type_name=_logon_type_name(logon_type),
                timestamp=evt_time,
                event_id=evt.get("event_id", 4624),
            )
    return None


def _current_user(user_sid, data):
    """Resolve the current console user from the lock event SID."""
    # If we have a username mapping from the PS1 data, use it
    user_map = data.get("sid_to_user", {})
    if user_sid in user_map:
        return user_map[user_sid].upper()
    # Fallback: extract username from SID suffix (last component)
    return user_sid.split("-")[-1] if user_sid else ""


def _screensaver_preceded(lock_time, data, window_secs=120):
    """Check if a screen saver event (4802) occurred shortly before the lock."""
    for evt in data.get("screensaver_events", []):
        if evt.get("event_id") != 4802:
            continue
        evt_time = _parse_time(evt.get("time", ""))
        delta = (lock_time - evt_time).total_seconds()
        if 0 <= delta <= window_secs:
            return True
    return False


def _sleep_preceded(lock_time, data, window_secs=30):
    """Check if a sleep/wake event occurred shortly before the lock."""
    for evt in data.get("power_events", []):
        evt_time = _parse_time(evt.get("time", ""))
        delta = (lock_time - evt_time).total_seconds()
        if 0 <= delta <= window_secs:
            return True
    return False


def _find_rdp_event(lock_time, rdp_events, window_secs=30):
    """Find an RDP session event within window_secs of the lock time."""
    window = timedelta(seconds=window_secs)
    for evt in rdp_events:
        evt_time = _parse_time(evt.get("time", ""))
        if abs(evt_time - lock_time) <= window:
            return evt
    return None


def _logon_type_name(logon_type):
    """Human-readable logon type name."""
    names = {
        2: "Interactive",
        3: "Network",
        4: "Batch",
        5: "Service",
        7: "Unlock",
        8: "NetworkCleartext",
        9: "NewCredentials",
        10: "RemoteInteractive (RDP)",
        11: "CachedInteractive",
        12: "CachedRemoteInteractive",
        13: "CachedUnlock",
    }
    return names.get(logon_type, f"Type {logon_type}")
