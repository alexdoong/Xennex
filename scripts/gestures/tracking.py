"""Single-hand tracking using the latest captured frame, with optional preview rendering."""
import time
from .capture import LatestFrame


class HandTracker:
    def __init__(self, index):
        import cv2
        import mediapipe as mp
        if not hasattr(mp, 'solutions'):
            raise RuntimeError('MediaPipe incompatível. Execute scripts/setup_gestures.ps1.')
        self.cv2, self.mp = cv2, mp
        def open_camera():
            # DirectShow objects are created, read and released by their owning thread.
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
            if not cap.isOpened():
                cap.release()
                raise RuntimeError('Câmera indisponível. Confira o índice e as permissões.')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        # One controlled hand avoids searching for a second missing hand on tracked frames.
        self.detector = mp.solutions.hands.Hands(max_num_hands=1, model_complexity=0,
            min_detection_confidence=0.7, min_tracking_confidence=0.7)
        try:
            self.capture = LatestFrame(open_camera)
        except Exception:
            self.detector.close()
            raise
        self.last_hand = None
        self.fresh = False
        self.preview_open = False
        self.landmarks = []
        self.metrics = {'fps': 0, 'inferenceMs': 0, 'frameAgeMs': 0}
        self.last_processed = None

    def read(self, preferred):
        latest = self.capture.take()
        self.fresh = latest is not None
        if latest is None:
            return None, None, None
        frame, captured = latest
        started = time.monotonic()
        if started - captured > .2:
            self.fresh = False
            return None, None, None
        frame = self.cv2.flip(frame, 1)
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self.detector.process(rgb)
        finished = time.monotonic()
        if self.last_processed is not None:
            fps = 1 / max(.001, finished - self.last_processed)
            self.metrics['fps'] = fps if not self.metrics['fps'] else .8 * self.metrics['fps'] + .2 * fps
        self.last_processed = finished
        self.metrics['inferenceMs'] = round((finished - started) * 1000, 1)
        self.metrics['frameAgeMs'] = round((finished - captured) * 1000, 1)
        detected = []
        self.landmarks = result.multi_hand_landmarks or []
        for landmarks, handedness in zip(self.landmarks, result.multi_handedness or []):
            detected.append((handedness.classification[0].label, [[p.x, p.y, p.z] for p in landmarks.landmark]))
        target = preferred if preferred != 'Any' else self.last_hand
        selected = next((p for p in detected if p[0] == target), None)
        if selected is None and detected and preferred == 'Any':
            selected = detected[0]
        self.last_hand = selected[0] if selected else None
        return frame, selected[1] if selected else None, self.last_hand

    def preview(self, frame, status):
        if frame is None:
            return False
        for landmarks in self.landmarks:
            self.mp.solutions.drawing_utils.draw_landmarks(frame, landmarks, self.mp.solutions.hands.HAND_CONNECTIONS)
        self.cv2.putText(frame, status, (12, 25), self.cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 240, 150), 2)
        self.cv2.imshow('Xennex Gestures - ESC: pausar | Q: fechar', frame)
        self.preview_open = True
        return self.cv2.waitKey(1) & 0xFF == ord('q')

    def hide_preview(self):
        if self.preview_open:
            self.cv2.destroyAllWindows()
            self.preview_open = False

    def close(self):
        self.capture.close()
        self.detector.close()
        self.hide_preview()
