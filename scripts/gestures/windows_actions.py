"""Native Win32 actions. Importing this module never moves the mouse or presses keys."""
import ctypes as c
from ctypes import wintypes as w
import time
from .smoothing import PointerFilter
from .action_errors import TargetUnavailable

KEYS = {'win': 0x5B, 'ctrl': 0x11, 'alt': 0x12, 'shift': 0x10, 'left': 0x25, 'up': 0x26,
        'right': 0x27, 'down': 0x28, 'enter': 0x0D, 'esc': 0x1B, 'space': 0x20, 'tab': 0x09,
        'backspace': 0x08, 'delete': 0x2E, 'home': 0x24, 'end': 0x23, 'pageup': 0x21,
        'pagedown': 0x22, 'playpause': 0xB3, 'volumeup': 0xAF, 'volumedown': 0xAE, 'mute': 0xAD}
KEYS.update({chr(i): i - 32 for i in range(97, 123)})
KEYS.update({str(i): 0x30 + i for i in range(10)})
KEYS.update({'f' + str(i): 0x6F + i for i in range(1, 25)})
ALIASES = {'windows': 'win', 'meta': 'win', 'control': 'ctrl', 'arrowleft': 'left',
           'arrowright': 'right', 'arrowup': 'up', 'arrowdown': 'down', 'escape': 'esc',
           'del': 'delete', 'return': 'enter'}


def parse_shortcut(value):
    keys = [ALIASES.get(key.strip().lower(), key.strip().lower()) for key in value.split('+')]
    if not 1 <= len(keys) <= 5 or len(set(keys)) != len(keys) or any(key not in KEYS for key in keys):
        raise ValueError('Atalho inválido. Exemplo: win+left ou ctrl+alt+m.')
    return [KEYS[key] for key in keys]


class MouseInput(c.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD), ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]


class KeyInput(c.Structure):
    _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]


class InputUnion(c.Union):
    _fields_ = [('mouse', MouseInput), ('key', KeyInput)]


class Input(c.Structure):
    _fields_ = [('type', w.DWORD), ('data', InputUnion)]


class WindowsActions:
    def __init__(self):
        self.user = c.WinDLL('user32', use_last_error=True)
        self.user.SendInput.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
        self.user.SendInput.restype = w.UINT
        self.user.WindowFromPoint.argtypes = [w.POINT]
        self.user.WindowFromPoint.restype = w.HWND
        self.user.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.user.GetAncestor.restype = w.HWND
        self.user.GetForegroundWindow.restype = w.HWND
        self.user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        self.user.IsWindow.argtypes = [w.HWND]
        self.user.IsZoomed.argtypes = [w.HWND]
        self.user.IsIconic.argtypes = [w.HWND]
        self.user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
        self.user.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, c.POINTER(c.c_size_t)]
        self.user.SendMessageTimeoutW.restype = c.c_ssize_t
        self.user.GetAsyncKeyState.argtypes = [c.c_int]
        try:
            self.user.SetProcessDpiAwarenessContext(c.c_void_p(-4))
        except AttributeError:
            pass
        self.drag = None
        self.mouse_down = False
        self.cursor = None
        self.pointer_filter = PointerFilter()
        self.scroll_y = None
        self.last_scroll = 0

    def emergency(self):
        return bool(self.user.GetAsyncKeyState(0x1B) & 0x8000)

    def send(self, packet):
        if self.user.SendInput(1, c.byref(packet), c.sizeof(Input)) != 1:
            raise OSError('Windows recusou a ação. Janelas elevadas podem exigir privilégios iguais.')

    def key(self, code, up=False):
        self.send(Input(1, InputUnion(key=KeyInput(code, 0, 2 if up else 0, 0, 0))))

    def mouse(self, flags, data=0):
        self.send(Input(0, InputUnion(mouse=MouseInput(0, 0, data & 0xFFFFFFFF, flags, 0, 0))))

    def shortcut(self, value):
        pressed = []
        try:
            for code in parse_shortcut(value):
                self.key(code)
                pressed.append(code)
        finally:
            release_error = None
            for code in reversed(pressed):
                try:
                    self.key(code, True)
                except OSError as error:
                    release_error = error
            if release_error:
                raise release_error

    def screen_point(self, position, smoothing):
        left, top = self.user.GetSystemMetrics(76), self.user.GetSystemMetrics(77)
        width, height = self.user.GetSystemMetrics(78), self.user.GetSystemMetrics(79)
        # Map the central 80% of the camera to the complete virtual desktop.
        x = left + min(1, max(0, (position[0] - 0.1) / 0.8)) * (width - 1)
        y = top + min(1, max(0, (position[1] - 0.1) / 0.8)) * (height - 1)
        if not hasattr(self, 'pointer_filter'):
            self.pointer_filter = PointerFilter()
        x, y = self.pointer_filter.feed(x, y, smoothing, time.monotonic())
        self.cursor = (x, y)
        return round(x), round(y)

    def release(self):
        self.drag = None
        self.cursor = None
        self.pointer_filter = PointerFilter()
        self.scroll_y = None
        if self.mouse_down:
            self.mouse_down = False
            self.mouse(0x0004)

    def execute(self, event, config):
        phase = event['phase']
        if phase == 'end':
            self.release()
            return
        action = event['gesture']['action']
        kind = action['type']
        if phase == 'trigger':
            if kind == 'shortcut':
                self.shortcut(action.get('value', ''))
            elif kind in ('click', 'right_click', 'double_click'):
                down, up = (0x0008, 0x0010) if kind == 'right_click' else (0x0002, 0x0004)
                for _ in range(2 if kind == 'double_click' else 1):
                    try:
                        self.mouse(down)
                    finally:
                        self.mouse(up)
            return
        x, y = self.screen_point(event['position'], config.get('smoothing', 0.45))
        if kind in ('pointer', 'drag_mouse'):
            if not self.user.SetCursorPos(x, y):
                raise OSError('Não foi possível mover o cursor.')
            if kind == 'drag_mouse' and not self.mouse_down:
                self.mouse_down = True
                self.mouse(0x0002)
        elif kind == 'drag_window':
            if phase == 'begin':
                target = self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(x, y)), 2)
                if config.get('dragTarget') == 'foreground':
                    target = self.user.GetForegroundWindow()
                else:
                    hit = c.c_size_t()
                    packed = (x & 0xFFFF) | ((y & 0xFFFF) << 16)
                    if not target or not self.user.SendMessageTimeoutW(target, 0x0084, 0, packed, 2, 100, c.byref(hit)) or hit.value != 2:
                        raise TargetUnavailable('Posicione o indicador na barra de título antes do pinch. Ou escolha “janela ativa”.')
                if not target or self.user.IsZoomed(target) or self.user.IsIconic(target):
                    raise TargetUnavailable('Restaure a janela antes de arrastar.')
                rect = w.RECT()
                if not self.user.GetWindowRect(target, c.byref(rect)):
                    raise OSError('Janela indisponível.')
                self.drag = (target, x, y, rect.left, rect.top)
            if self.drag:
                target, start_x, start_y, left, top = self.drag
                if not self.user.IsWindow(target):
                    self.release()
                    return
                if not self.user.SetWindowPos(target, None, left + x - start_x, top + y - start_y, 0, 0, 0x4015):
                    raise OSError('Windows recusou mover esta janela.')
        elif kind == 'scroll':
            now = time.monotonic()
            if self.scroll_y is not None and abs(y - self.scroll_y) > 18 and now - self.last_scroll > 0.08:
                self.mouse(0x0800, 120 if y < self.scroll_y else -120)
                self.last_scroll = now
                self.scroll_y = y
            if self.scroll_y is None:
                self.scroll_y = y
