"""
Is a newer Caelum waiting in the Snap Store? snapd installs it only once Caelum closes, and Caelum
runs all session long, so the snap says so on screen. The request goes to the store snapd already
talks to and carries nothing about the user.
"""

import re

from .net import get_json

_URL = 'https://api.snapcraft.io/v2/snaps/info/{}?fields=version,revision'
_RISKS = ('stable', 'candidate', 'beta', 'edge')
_NAME = re.compile(r'^[a-z0-9-]{1,40}$')


def waiting(channel_map, revision, arch, track='latest'):
    """
    The version of a newer release on the channel this revision most likely came from, or None.
    A snap can't see which channel it tracks: it is taken to be the least risky one at or past
    this revision, so a stable user is never pointed at a beta.
    """
    releases = {}
    for entry in channel_map if isinstance(channel_map, list) else []:
        try:
            ch = entry['channel']
            if ch['architecture'] == arch and ch['track'] == track and ch['risk'] in _RISKS:
                releases[ch['risk']] = (int(entry['revision']), str(entry['version'])[:32])
        except (KeyError, TypeError, ValueError):
            continue
    for risk in _RISKS:
        if risk in releases and releases[risk][0] >= revision:
            rev, version = releases[risk]
            return version if rev > revision else None
    return None


def check(name, revision, arch):
    """waiting() from the store's answer; None when up to date or the store can't be reached."""
    if not _NAME.match(name):
        return None
    try:
        data = get_json(_URL.format(name), headers={'Snap-Device-Series': '16'})
        return waiting(data.get('channel-map'), revision, arch)
    except Exception:
        return None
