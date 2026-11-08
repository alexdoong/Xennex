"""Commands are queued; recognition and desktop actions run on one frame thread."""
import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path
from .recognition import GestureEngine
from .recording import Recorder
from .control import ControlSession
from .action_errors import TargetUnavailable

_output_lock = threading.Lock()

def emit(kind, **data):
    with _output_lock:
        print(json.dumps({'type': kind, **data}, ensure_ascii=True, allow_nan=False), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--config', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        import cv2
        import mediapipe as mp
        if not hasattr(mp, 'solutions'):
            raise RuntimeError('MediaPipe incompatível: use setup_gestures.ps1.')
        import numpy as np
        # Exercise the actual graph and packaged model assets without requesting camera access.
        with mp.solutions.hands.Hands(static_image_mode=True, model_complexity=0) as detector:
            detector.process(np.zeros((480, 640, 3), dtype=np.uint8))
        emit('check', message=f'OpenCV {cv2.__version__}; MediaPipe {mp.__version__}; modelo de mãos carregado')
        return
    from .tracking import HandTracker
    from .windows_actions import WindowsActions
    commands = queue.Queue()
    def listen():
        for line in sys.stdin:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    commands.put(value)
            except ValueError:
                emit('error', message='Comando inválido recebido.')
        commands.put({'type': 'stop'})
    threading.Thread(target=listen, daemon=True).start()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    engine = GestureEngine(config)
    actions = WindowsActions()
    tracker, recorder = None, None
    control = ControlSession(actions)
    running = True
    watchdog_stop = threading.Event()
    def watch():
        while not watchdog_stop.wait(0.1):
            try:
                if control.watchdog():
                    emit('status', message='Controle pausado: ' + (control.pause_reason or 'captura interrompida') + '.', armed=False)
            except Exception as error:
                emit('error', message=str(error))
    watchdog_thread = threading.Thread(target=watch, daemon=True)
    watchdog_thread.start()
    last_status, last_match = 0, ''
    last_fresh = time.monotonic()
    recognition_ms = 0
    try:
        emit('status', message='Abrindo câmera', armed=False)
        tracker = HandTracker(args.camera)
        emit('status', message='Câmera pronta. Modo de teste.', armed=False)
        while running:
            now = time.monotonic()
            while not commands.empty():
                command = commands.get_nowait()
                kind = command.get('type')
                if kind == 'stop':
                    running = False
                elif kind == 'arm':
                    engine.reset()
                    control.arm(command.get('enabled') is True and recorder is None)
                    emit('status', message='Controle ativo. Esc pausa.' if control.armed else 'Modo de teste.', armed=control.armed)
                elif kind == 'reload':
                    control.arm(False)
                    recorder = None
                    config = json.loads(path.read_text(encoding='utf-8-sig'))
                    engine = GestureEngine(config)
                elif kind == 'record':
                    gesture = next((g for g in config['gestures'] if g['id'] == command.get('id')), None)
                    if gesture and gesture['source'] in ('pose', 'motion'):
                        control.arm(False)
                        engine.reset()
                        recorder = Recorder(gesture['id'], gesture['source'], now)
                        recorder.token = command.get('token')
                    else:
                        emit('error', message='Escolha uma pose ou movimento personalizado.')
                elif kind == 'cancel':
                    recorder = None
                    engine.reset()
                    control.arm(False)
                    emit('recording', stage='cancelled', remaining=0)
            if not running:
                break
            frame, points, hand = tracker.read(config.get('hand', 'Any'))
            now = time.monotonic()
            if not tracker.fresh:
                if recorder and now >= recorder.start and now - last_fresh > .3:
                    recorder = None
                    emit('error', message='A captura interrompeu durante a amostra. Grave novamente.')
                if now - last_fresh > .2:
                    for event in engine.reset():
                        control.execute(event, config)
                    if now - last_status > .1:
                        emit('frame', points=None, hand=None, armed=control.armed, match=last_match,
                             recording=recorder is not None, metrics={**tracker.metrics, 'fps': 0, 'frameAgeMs': round((now-last_fresh)*1000)})
                        last_status = now
                continue
            last_fresh = now
            if control.heartbeat():
                engine.reset()
            if recorder:
                result = recorder.feed(points, now, hand)
                if result['stage'] == 'done':
                    emit('recorded', id=recorder.id, token=recorder.token, sample=result['sample'])
                    recorder = None
                elif result['stage'] == 'error':
                    emit('error', message=result['message'])
                    recorder = None
                elif now - last_status > 0.033:
                    emit('recording', **result)
            else:
                recognition_start = time.perf_counter()
                events = engine.feed(points, now, hand)
                recognition_ms = round((time.perf_counter() - recognition_start) * 1000, 2)
                for event in events:
                    last_match = event['gesture']['name']
                    if event['phase'] in ('begin', 'trigger'):
                        emit('recognized', name=last_match, phase=event['phase'], executed=control.armed)
                    if control.armed or event['phase'] == 'end':
                        try:
                            control.execute(event, config)
                        except TargetUnavailable as error:
                            engine.reject_current()
                            emit('status', message=str(error), armed=control.armed)
                            break
                        except Exception as error:
                            control.arm(False)
                            engine.reset()
                            emit('error', message=str(error))
                            break
            if now - last_status > 0.033:
                emit('frame', points=points, hand=hand, armed=control.armed, match=last_match, recording=recorder is not None,
                     metrics={**tracker.metrics, 'recognitionMs': recognition_ms})
                last_status = now
            if config.get('preview', False) and tracker.preview(frame, 'ATIVO' if control.armed else 'TESTE'):
                break
            if not config.get('preview', False):
                tracker.hide_preview()

    finally:
        watchdog_stop.set()
        try:
            control.arm(False)
        finally:
            if tracker:
                tracker.close()
            emit('stopped', armed=False)

def run():
    try:
        main()
    except Exception as error:
        emit('error', message=str(error) + ' Se faltarem dependências, execute scripts/setup_gestures.ps1.')
        sys.exit(1)
