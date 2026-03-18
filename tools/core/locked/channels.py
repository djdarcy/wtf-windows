"""wtf-locked channel definitions for the THAC0 verbosity system.

Defines the output channels specific to lock diagnosis. The THAC0 library
(wtf_windows.lib.log_lib) is project-agnostic; channel names and descriptions
are registered here at the tool layer.
"""

# Channels for wtf-locked output domains
CHANNELS = {
    'verdict',      # Lock verdict determination and display
    'evidence',     # Evidence collection and summary
    'session',      # Lock/unlock session details and timeline
    'login',        # Concurrent login details (who, from where, what IP)
    'rdp',          # RDP session events and connection details
    'policy',       # Registry settings, GPO, audit policy status
    'history',      # Lock/unlock history timeline
    'ai',           # AI analysis progress and results (future)
    'progress',     # Progress indicators
    'hint',         # Contextual tips and guidance
    'error',        # Error messages
    'trace',        # Function tracing
    'general',      # Default channel
}

CHANNEL_DESCRIPTIONS = {
    'verdict':   'Lock verdict and threat assessment',
    'evidence':  'Evidence supporting the verdict',
    'session':   'Lock/unlock session details and durations',
    'login':     'Concurrent login details (user, source, auth type)',
    'rdp':       'RDP session events and remote connection info',
    'policy':    'Registry, GPO, screen saver, and audit policy settings',
    'history':   'Lock/unlock timeline',
    'ai':        'AI analysis (future)',
    'progress':  'Progress indicators',
    'hint':      'Contextual tips and security guidance',
    'error':     'Error messages',
    'trace':     'Function call tracing',
    'general':   'General output',
}

# Channels off by default (require explicit --show)
OPT_IN_CHANNELS = {
    'trace',    # Function call tracing -- opt-in (verbose debug output)
}
