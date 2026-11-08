"""Pinned local Windows Mirage geometry provider for the finite perception worker."""
import ctypes
import hashlib
import json
import platform
import sys
from pathlib import Path

from .mirage_regions import select_boxes

DLL = 'libcactus.dll'
WEIGHTS = 'mirage.cact'
ASSETS = {
    DLL: (1863168, '21bfd175a0f1827bb05eb61e43f8cae5e4f28ca0930a3762c6ac5270d2fbee17'),
    WEIGHTS: (21611043, '4249a0f7515272ff76b9414bec17d7e7daf84b15b66c7fb4f17fce1e66f9f237'),
}
OPTIONS = json.dumps({'sections': ['objects'], 'fields': ['bbox', 'score'], 'max_objects': 16,
                      'max_tokens': 128}).encode('ascii')


def verified_file(folder, name):
    path = folder / name
    size, digest = ASSETS[name]
    if path.is_symlink() or path.resolve().parent != folder or path.stat().st_size != size:
        raise ValueError('Invalid local Mirage asset.')
    with path.open('rb') as stream:
        data = stream.read(size + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Local Mirage asset differs from the pinned Windows release.')
    return data


class MirageDetector:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.lib = None
        self.unavailable = False

    def load(self):
        if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64') or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ValueError('The pinned Mirage runtime requires Windows x64.')
        verified_file(self.folder, DLL)
        data = verified_file(self.folder, WEIGHTS)
        lib = ctypes.CDLL(str(self.folder / DLL))
        lib.cactus_load.argtypes = [ctypes.c_char_p, ctypes.c_ulonglong]
        lib.cactus_models.argtypes = []
        lib.cactus_describe.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p,
                                        ctypes.c_char_p, ctypes.POINTER(ctypes.c_char), ctypes.c_int]
        if lib.cactus_load(data, len(data)) < 0 or not lib.cactus_models() & 4:
            raise RuntimeError('Local Mirage runtime could not load the vision model.')
        return lib

    def boxes(self, image):
        if self.unavailable:
            raise RuntimeError('Local Mirage runtime is unavailable for this batch.')
        if self.lib is None:
            try:
                self.lib = self.load()
            except (OSError, ValueError, RuntimeError, AttributeError):
                self.unavailable = True
                raise RuntimeError('Local Mirage runtime is unavailable for this batch.') from None
        output = ctypes.create_string_buffer(262144)
        if self.lib.cactus_describe(image.tobytes(), *image.size, OPTIONS, None, None, output, len(output)) < 0:
            raise RuntimeError('Local Mirage inference failed.')
        return select_boxes(json.loads(output.value), *image.size, skip_scene=True)
