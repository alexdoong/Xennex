"""Synthetic landmarks and fake input adapters only: never opens a camera or controls the desktop."""
import copy
import ctypes
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestures.features import shape, shape_distance, sequence_distance, valid_hand
from gestures.recognition import GestureEngine
from gestures.recording import Recorder
from gestures.control import ControlSession
from gestures.windows_actions import WindowsActions, parse_shortcut, Input
from ctypes import wintypes


def hand(kind='palm', dx=0):
    p = [[.5,.8,0], [.43,.73,0], [.39,.65,0], [.34,.60,0], [.28,.57,0],
         [.43,.64,0], [.42,.50,0], [.42,.4,0], [.42,.3,0],
         [.50,.62,0], [.50,.46,0], [.50,.34,0], [.50,.24,0],
         [.57,.64,0], [.58,.50,0], [.58,.4,0], [.58,.3,0],
         [.64,.67,0], [.66,.57,0], [.68,.49,0], [.70,.4,0]]
    if kind in ('point', 'fist'):
        for i in (12,16,20):
            p[i][1] = .72
    if kind == 'fist':
        p[8][1] = .73
    if kind == 'pinch':
        p[4] = [p[8][0] + .02, p[8][1], 0]
    return [[x + dx, y, z] for x,y,z in p]


def binding(source='pinch', action='drag_window', name='one', samples=None):
    return {'id': name, 'name': name, 'source': source, 'enabled': True, 'holdMs': 200,
            'cooldownMs': 1000, 'threshold': .18, 'action': {'type': action, 'value': 'win+left'},
            'samples': samples or []}


def engine(*gestures):
    return GestureEngine({'gestures': list(gestures), 'hand': 'Any', 'swipeThreshold': .18})


class GeometryTests(unittest.TestCase):
    def test_shape_ignores_translation_and_scale(self):
        points = hand()
        transformed = [[x * 1.5 + 2, y * 1.5 - 3, z * 1.5] for x,y,z in points]
        self.assertAlmostEqual(shape_distance(shape(points), shape(transformed)), 0)
        self.assertGreater(shape_distance(shape(points), shape(hand('fist'))), .18)

    def test_invalid_landmarks_end_active_input(self):
        e = engine(binding())
        e.feed(hand('pinch'), 0)
        e.feed(hand('pinch'), .3)
        invalid = hand('pinch'); invalid[0][0] = float('nan')
        self.assertFalse(valid_hand(invalid))
        self.assertEqual([v['phase'] for v in e.feed(invalid, .4)], ['end'])

    def test_motion_retains_direction_but_accepts_speed_and_position_changes(self):
        slow = [hand('fist', i * .02) for i in range(16)]
        fast = [hand('fist', i * .06 + .2) for i in range(6)]
        self.assertLess(sequence_distance(slow, fast), .06)
        self.assertGreater(sequence_distance(slow, list(reversed(slow))), .3)


class RecognitionTests(unittest.TestCase):
    def test_continuous_pinch_release_and_hysteresis(self):
        e = engine(binding())
        self.assertEqual(e.feed(hand('pinch'), 0), [])
        self.assertEqual(e.feed(hand('pinch'), .21)[0]['phase'], 'begin')
        jitter = hand('pinch'); jitter[4][0] = jitter[8][0] + .07
        self.assertEqual(e.feed(jitter, .3)[0]['phase'], 'update')
        self.assertEqual(e.feed(None, .4)[0]['phase'], 'end')
        self.assertEqual(e.feed(None, .5), [])

    def test_hand_switch_releases_before_reacquiring(self):
        e = engine(binding())
        e.feed(hand('pinch'), 0, 'Right'); e.feed(hand('pinch'), .3, 'Right')
        self.assertEqual(e.feed(hand('pinch'), .4, 'Left')[0]['phase'], 'end')
        self.assertEqual(e.feed(hand('pinch'), .5, 'Left'), [])

    def test_shortcut_is_latched_until_neutral(self):
        e = engine(binding('open_palm', 'shortcut'))
        events = []
        for i in range(40): events += e.feed(hand(), i * .1)
        self.assertEqual(len([v for v in events if v['phase'] == 'trigger']), 1)
        e.feed(hand('fist'), 4); e.feed(hand('fist'), 4.3)
        e.feed(hand(), 4.4)
        self.assertEqual(e.feed(hand(), 4.7)[0]['phase'], 'trigger')

    def test_swipe_direction_dominance_and_cooldown(self):
        e = engine(binding('swipe_right', 'shortcut', 'right'), binding('swipe_left', 'shortcut', 'left'))
        events = []
        for t, dx in [(0,0),(.1,.09),(.2,.20),(.3,.3)]:
            events += e.feed(hand(dx=dx), t)
        self.assertEqual([v['gesture']['id'] for v in events], ['right'])
        for t, dx in [(.4,.0),(.5,.1),(.6,.3)]: events += e.feed(hand(dx=dx), t)
        self.assertEqual(len(events), 1)
        e.reset()
        diagonal = hand(dx=.25)
        for p in diagonal: p[1] += .25
        e.feed(hand(), 2); e.feed(hand(dx=.1), 2.1)
        self.assertEqual(e.feed(diagonal, 2.2), [])

    def test_learned_pose_has_priority_and_ambiguous_poses_do_nothing(self):
        sample = {'frames': [hand('point')], 'duration': 1}
        learned = binding('pose', 'shortcut', 'learned', [sample])
        e = engine(binding('point', 'pointer', 'builtin'), learned)
        e.feed(hand('point'), 0)
        self.assertEqual(e.feed(hand('point'), .3)[0]['gesture']['id'], 'learned')
        twin = copy.deepcopy(learned); twin['id'] = 'twin'
        e = engine(learned, twin)
        e.feed(hand('point'), 0)
        self.assertEqual(e.feed(hand('point'), .3), [])

    def test_learned_motion_can_trigger(self):
        frames = [hand('fist', i * .02) for i in range(16)]
        e = engine(binding('motion', 'shortcut', 'move', [{'frames': frames, 'duration': 1.5}]))
        events = []
        for i, points in enumerate(frames): events += e.feed(points, i * .1)
        self.assertTrue(any(v['phase'] == 'trigger' for v in events))

    def test_disabled_and_wrong_hand_never_match(self):
        g = binding(); g['enabled'] = False
        e = engine(g)
        e.feed(hand('pinch'), 0)
        self.assertEqual(e.feed(hand('pinch'), 1), [])
        g['enabled'] = True; e.config['hand'] = 'Left'
        self.assertEqual(e.feed(hand('pinch'), 2, 'Right'), [])


class RecordingTests(unittest.TestCase):
    def test_countdown_and_bounded_pose_sample(self):
        r = Recorder('x', 'pose', 0)
        self.assertEqual(r.feed(None, 2, None)['stage'], 'countdown')
        for i in range(11): result = r.feed(hand(), 3 + i / 10, 'Right')
        self.assertEqual(result['stage'], 'done')
        self.assertEqual(len(result['sample']['frames']), 8)

    def test_recording_rejects_tracking_loss_and_handover(self):
        r = Recorder('x', 'motion', 0)
        r.feed(hand(), 3, 'Right')
        self.assertEqual(r.feed(None, 3.1, None)['stage'], 'error')
        self.assertEqual(r.feed(hand(), 3.1, 'Left')['stage'], 'error')

    def test_static_hand_is_not_a_motion(self):
        r = Recorder('x', 'motion', 0)
        for i in range(21): result = r.feed(hand(), 3 + i / 10, 'Right')
        self.assertEqual(result['stage'], 'error')

    def test_low_frame_rate_is_rejected(self):
        r = Recorder('x', 'pose', 0)
        r.feed(hand(), 3, 'Right')
        self.assertEqual(r.feed(hand(), 3.5, 'Right')['stage'], 'error')


class FakeActions:
    def __init__(self): self.events = []; self.escape = False
    def release(self): self.events.append('release')
    def emergency(self): return self.escape
    def execute(self, event, config): self.events.append(event['phase'])


class ControlTests(unittest.TestCase):
    def test_dry_run_and_lease_timeout(self):
        actions = FakeActions(); now = [0]
        c = ControlSession(actions, lambda: now[0])
        event = {'phase': 'begin'}
        c.execute(event, {})
        self.assertEqual(actions.events, [])
        c.arm(True); c.execute(event, {})
        self.assertEqual(actions.events, ['release', 'begin'])
        now[0] = 1
        c.execute(event, {})
        self.assertFalse(c.armed)
        self.assertEqual(actions.events[-1], 'release')

    def test_escape_pauses_and_heartbeat_does_not_rearm(self):
        actions = FakeActions(); c = ControlSession(actions, lambda: 0)
        c.arm(True); actions.escape = True
        self.assertTrue(c.watchdog())
        actions.escape = False
        c.heartbeat()
        self.assertFalse(c.armed)

    def test_execution_failure_releases(self):
        class Failure(FakeActions):
            def execute(self, event, config): raise OSError('refused')
        c = ControlSession(Failure(), lambda: 0); c.arm(True)
        with self.assertRaises(OSError): c.execute({'phase': 'begin'}, {})
        self.assertFalse(c.armed)
        self.assertEqual(c.actions.events[-1], 'release')


class NativeAdapterTests(unittest.TestCase):
    def test_shortcut_validation_and_input_layout(self):
        self.assertEqual(parse_shortcut('Windows+ArrowLeft'), [0x5B, 0x25])
        for value in ('', 'ctrl+ctrl', 'run:format', 'ctrl+unknown'):
            with self.assertRaises(ValueError): parse_shortcut(value)
        if sys.platform == 'win32' and ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(Input), 40)

    def test_all_pressed_keys_are_released_after_failure(self):
        actions = WindowsActions.__new__(WindowsActions)
        seen = []
        def key(code, up=False):
            seen.append((code, up))
            if code == 0x25 and not up: raise OSError('down failed')
        actions.key = key
        with self.assertRaises(OSError): actions.shortcut('ctrl+win+left')
        self.assertEqual(seen[-2:], [(0x5B, True), (0x11, True)])

    def test_other_keys_release_even_when_one_key_up_fails(self):
        actions = WindowsActions.__new__(WindowsActions)
        seen = []
        def key(code, up=False):
            seen.append((code, up))
            if code == 0x25 and up: raise OSError('up failed')
        actions.key = key
        with self.assertRaises(OSError): actions.shortcut('ctrl+win+left')
        self.assertEqual(seen[-1], (0x11, True))

    def test_window_drag_uses_initial_rect_and_stops_on_release(self):
        class User:
            def __init__(self): self.positions = []
            def GetSystemMetrics(self, index): return {76:0,77:0,78:1001,79:801}[index]
            def WindowFromPoint(self, p): return 1
            def GetAncestor(self, target, level): return target
            def GetForegroundWindow(self): return 0x100000001
            def IsZoomed(self, target): return False
            def IsIconic(self, target): return False
            def IsWindow(self, target): return True
            def GetWindowRect(self, target, ptr):
                rect = ctypes.cast(ptr, ctypes.POINTER(wintypes.RECT)).contents
                rect.left, rect.top = 100, 200
                return True
            def SetWindowPos(self, *values): self.positions.append(values); return True
        actions = WindowsActions.__new__(WindowsActions)
        actions.user = User()
        actions.drag = actions.cursor = actions.scroll_y = None
        actions.mouse_down = False
        config = {'dragTarget': 'foreground', 'smoothing': 0}
        event = {'phase': 'begin', 'gesture': binding(), 'position': [.5,.5]}
        actions.execute(event, config)
        event.update(phase='update', position=[.6,.6]); actions.execute(event, config)
        self.assertEqual(actions.user.positions[-1][2:4], (225, 300))
        actions.execute({'phase':'end'}, config)
        self.assertIsNone(actions.drag)
        actions.execute(event, config)
        self.assertEqual(len(actions.user.positions), 2)


if __name__ == '__main__':
    unittest.main()
