"""
Telling the user about a daily run's problems: a Windows notification ("toast", using only what
Windows ships with; the scheduled task runs while the user is logged on), and on a server, where
nobody sees one, an e-mail to ALERT_EMAIL. Never raises: a notification problem must not break
the scraper run.
"""
import logging
import os
import subprocess
import sys

from app import config
from app.services import mail_service

log = logging.getLogger(__name__)

# PowerShell's own app id: toasts from unregistered app ids are not shown on Windows 10/11.
# Title and message come in through environment variables, so no text is pasted into the script.
TOAST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $xml.GetElementsByTagName('text')
$texts.Item(0).AppendChild($xml.CreateTextNode($env:TOAST_TITLE)) > $null
$texts.Item(1).AppendChild($xml.CreateTextNode($env:TOAST_MESSAGE)) > $null
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notify(title, message):
    """A Windows notification on Windows, and an e-mail when ALERT_EMAIL is set."""
    if config.ALERT_EMAIL:
        try:
            mail_service.send(config.ALERT_EMAIL, title, message)
        except Exception as e:
            log.warning("Could not e-mail the run's problems: %s", e)
    if sys.platform == "win32":
        toast(title, message)


def toast(title, message):
    """Show a Windows notification. Returns True if it was shown."""

    env = dict(os.environ, TOAST_TITLE=title[:100], TOAST_MESSAGE=message[:300])
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", TOAST_SCRIPT],
            env=env, capture_output=True, timeout=30, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as e:
        log.warning("Could not show the Windows notification: %s", e)
        return False


def run_summary(failed, warnings):
    """Notification text for a daily run, or None when every store was fine."""
    if not failed and not warnings:
        return None
    parts = []
    if failed:
        parts.append(f"Falhou: {', '.join(failed)}")
    if warnings:
        parts.append(f"Com problemas (produtos em falta): {', '.join(warnings)}")
    return "Game Price Tracker", " · ".join(parts) + ". Ver logs\\scraper-<data>.log"
