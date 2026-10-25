import os
import unittest
from unittest import mock

from caelum.core import snapstore
from caelum.gtk_ui import sandbox


def channel(risk, rev, version, arch='amd64', track='latest'):
    return {'channel': {'architecture': arch, 'name': risk, 'risk': risk, 'track': track},
            'revision': rev, 'version': version}


MAP = [channel('stable', 11, '1.5.3'), channel('beta', 12, '1.5.4')]


class WaitingTest(unittest.TestCase):
    def test_stable_user_is_not_sent_to_beta(self):
        self.assertIsNone(snapstore.waiting(MAP, 11, 'amd64'))

    def test_stable_update(self):
        self.assertEqual(snapstore.waiting(MAP, 9, 'amd64'), '1.5.3')

    def test_beta_user_past_stable(self):
        m = [channel('stable', 9, '1.5.1'), channel('beta', 12, '1.5.4')]
        self.assertEqual(snapstore.waiting(m, 11, 'amd64'), '1.5.4')

    def test_up_to_date_or_ahead(self):
        self.assertIsNone(snapstore.waiting(MAP, 12, 'amd64'))
        self.assertIsNone(snapstore.waiting(MAP, 13, 'amd64'))

    def test_other_architectures_and_tracks_are_ignored(self):
        m = [channel('stable', 11, '1.5.3'), channel('stable', 20, '9', arch='arm64'),
             channel('stable', 21, '9', track='2.x')]
        self.assertIsNone(snapstore.waiting(m, 11, 'amd64'))

    def test_garbage(self):
        self.assertIsNone(snapstore.waiting(None, 1, 'amd64'))
        self.assertIsNone(snapstore.waiting([{'channel': 'x'}, {'revision': 'n'}, 5], 1, 'amd64'))

    def test_check(self):
        with mock.patch.object(snapstore, 'get_json', return_value={'channel-map': MAP}) as get:
            self.assertEqual(snapstore.check('caelum', 9, 'amd64'), '1.5.3')
        url = get.call_args[0][0]
        self.assertTrue(url.startswith('https://api.snapcraft.io/v2/snaps/info/caelum?'))
        self.assertEqual(get.call_args[1]['headers'], {'Snap-Device-Series': '16'})
        with mock.patch.object(snapstore, 'get_json', side_effect=OSError):
            self.assertIsNone(snapstore.check('caelum', 9, 'amd64'))
        self.assertIsNone(snapstore.check('../x', 9, 'amd64'))


class SnapIdentityTest(unittest.TestCase):
    def identity(self, **env):
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sandbox.os.path, 'exists', return_value=False):
            return sandbox.snap_identity()

    def test_store_snap(self):
        self.assertEqual(self.identity(SNAP_NAME='caelum', SNAP_REVISION='11', SNAP_ARCH='amd64'),
                         ('caelum', 11, 'amd64'))

    def test_local_build_and_plain_install(self):
        self.assertIsNone(self.identity(SNAP_NAME='caelum', SNAP_REVISION='x1', SNAP_ARCH='amd64'))
        self.assertIsNone(self.identity())


if __name__ == '__main__':
    unittest.main()
