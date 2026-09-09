import cv2
import mediapipe as mp
import pyautogui
import math
import sys
import time
import argparse
import threading
import json
import os
os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data'), exist_ok=True)
import numpy as np

# Logging setup
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'hand_motion_log.txt')
def log_msg(msg):
    print(msg, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")

try:
    # Disable fail-safe to prevent crash if mouse hits corner
    pyautogui.FAILSAFE = False

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0, help="Camera index to use")
    args = parser.parse_args()

    # Gesture Configuration
    GESTURES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'gestures.json')
    gestures = {}
    recording_pending_action = None

    def load_gestures():
        global gestures
        try:
            if os.path.exists(GESTURES_FILE):
                with open(GESTURES_FILE, 'r') as f:
                    gestures = json.load(f)
                    log_msg(f"[INFO] Loaded {len(gestures)} gestures.")
        except Exception as e:
            log_msg(f"[ERROR] Failed to load gestures: {e}")

    SWIPE_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Data', 'swipe_config.json')
    swipe_config = {}

    def load_swipe_config():
        global swipe_config
        try:
            if os.path.exists(SWIPE_CONFIG_FILE):
                with open(SWIPE_CONFIG_FILE, 'r') as f:
                    swipe_config = json.load(f)
                    log_msg(f"[INFO] Loaded swipe config: {swipe_config}")
        except Exception as e:
            log_msg(f"[ERROR] Failed to load swipe config: {e}")

    load_swipe_config()

    def save_gestures():
        try:
            with open(GESTURES_FILE, 'w') as f:
                json.dump(gestures, f, indent=4)
                log_msg("[INFO] Gestures saved successfully.")
        except Exception as e:
            log_msg(f"[ERROR] Failed to save gestures: {e}")

    load_gestures()

    # Listen to stdin for commands from C# backend
    def stdin_listener():
        global recording_pending_action
        for line in sys.stdin:
            cmd = line.strip()
            if cmd.startswith("RECORD_GESTURE:"):
                action = cmd.split(":", 1)[1]
                recording_pending_action = action
                log_msg(f"[INFO] Command received to record gesture for: {action}")
            elif cmd.startswith("DELETE_GESTURE:"):
                action = cmd.split(":", 1)[1]
                if action in gestures:
                    del gestures[action]
                    save_gestures()
                    log_msg(f"[INFO] Deleted gesture: {action}")
                else:
                    log_msg(f"[WARNING] Tried to delete unknown gesture: {action}")
            elif cmd == "RELOAD_SWIPES":
                load_swipe_config()
                log_msg("[INFO] Reloaded swipe configuration.")

    # Start listener thread
    threading.Thread(target=stdin_listener, daemon=True).start()

    # 1. Initialize the camera and the MediaPipe hand model
    log_msg(f"[INFO] Attempting to open camera at index {args.camera}...")
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        log_msg(f"[WARNING] DSHOW failed, trying MSMF for camera {args.camera}...")
        cap = cv2.VideoCapture(args.camera, cv2.CAP_MSMF)
        
    if not cap.isOpened():
        log_msg(f"[ERROR] Cannot open webcam at index {args.camera}.")
        sys.exit(1)

    log_msg("[INFO] Camera opened successfully.")

    mp_hands = mp.solutions.hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7
    )

    screen_w, screen_h = pyautogui.size()
    log_msg(f"[INFO] Hand Motion controller started on Camera {args.camera}.")
    log_msg(f"[INFO] Screen resolution: {screen_w}x{screen_h}")

    prev_x, prev_y = 0, 0
    smoothing_factor = 0.5
    last_action_time = 0

    KEY_ALIASES = {
        'windows': 'win',
        'winleft': 'win',
        'winright': 'win',
        'cmd': 'win',
        'super': 'win',
        'meta': 'win',
        'arrowleft': 'left',
        'arrowright': 'right',
        'arrowup': 'up',
        'arrowdown': 'down',
        'control': 'ctrl',
        'escape': 'esc',
        'return': 'enter'
    }

    def execute_action(action):
        global last_action_time
        now = time.time()
        if now - last_action_time < 1.0:
            return # Cooldown
        
        log_msg(f"[ACTION] Executing gesture action: {action}")
        try:
            if action.startswith("KEYBOARD:"):
                keys_str = action[len("KEYBOARD:"):]
                keys = [k.strip().lower() for k in keys_str.split("+") if k.strip()]
                normalized_keys = [KEY_ALIASES.get(k, k) for k in keys]
                if normalized_keys:
                    log_msg(f"[ACTION] Pressing hotkey: {normalized_keys}")
                    pyautogui.hotkey(*normalized_keys)
            elif action == "Play/Pause":
                pyautogui.press('playpause')
            elif action == "Volume Up":
                pyautogui.press('volumeup')
                pyautogui.press('volumeup')
            elif action == "Volume Down":
                pyautogui.press('volumedown')
                pyautogui.press('volumedown')
            elif action == "Mute":
                pyautogui.press('volumemute')
        except Exception as e:
            log_msg(f"[ERROR] Action execution failed: {e}")
            
        last_action_time = now

    def normalize_landmarks(landmarks):
        wrist = landmarks.landmark[0]
        points = []
        for lm in landmarks.landmark:
            points.append([lm.x - wrist.x, lm.y - wrist.y])
        
        max_dist = 0
        for p in points:
            dist = math.hypot(p[0], p[1])
            if dist > max_dist:
                max_dist = dist
                
        if max_dist == 0: max_dist = 1
        
        normalized = []
        for p in points:
            normalized.append([p[0] / max_dist, p[1] / max_dist])
            
        return normalized

    recording_start_time = 0
    recording_action = None

    active_continuous_action = None
    target_window = None

    swipe_history = []
    swipe_cooldown_until = 0

    while True:
        success, frame = cap.read()
        if not success:
            log_msg("[ERROR] Failed to read from camera.")
            break
            
        frame = cv2.flip(frame, 1)
        
        if recording_pending_action:
            recording_action = recording_pending_action
            recording_pending_action = None
            recording_start_time = time.time()
            log_msg(f"[INFO] Get ready to perform gesture for {recording_action}. Recording in 3 seconds...")
            
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = mp_hands.process(rgb_frame)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                if recording_action and (time.time() - recording_start_time) > 3.0:
                    log_msg(f"[INFO] Recording gesture for {recording_action} NOW!")
                    norm_lm = normalize_landmarks(hand_landmarks)
                    gestures[recording_action] = norm_lm
                    save_gestures()
                    recording_action = None
                    log_msg(f"[INFO] Gesture recorded and saved successfully!")
                    
                if not recording_action:
                    norm_lm = normalize_landmarks(hand_landmarks)
                    
                    best_match = None
                    best_dist = float('inf')
                    
                    for g_action, g_points in gestures.items():
                        if len(g_points) != 21: continue
                        
                        total_dist = 0
                        for i in range(21):
                            d = math.hypot(norm_lm[i][0] - g_points[i][0], norm_lm[i][1] - g_points[i][1])
                            total_dist += d
                        
                        avg_dist = total_dist / 21.0
                        if avg_dist < best_dist:
                            best_dist = avg_dist
                            best_match = g_action
                    
                        # log_msg(f"Dist to {g_action}: {avg_dist}")

                    if best_match and best_dist < 0.15:
                        active_continuous_action = best_match
                        if best_match not in ["MoveMouse", "MoveWindow", "SwipeMode"]:
                            execute_action(best_match)
                    else:
                        active_continuous_action = None

                index_finger = hand_landmarks.landmark[8]
                thumb = hand_landmarks.landmark[4]
                wrist = hand_landmarks.landmark[0]

                raw_x = index_finger.x * screen_w
                raw_y = index_finger.y * screen_h

                # Dynamic Swipe Tracking Logic
                current_time = time.time()
                if active_continuous_action == "SwipeMode":
                    if current_time > swipe_cooldown_until:
                        swipe_history.append((wrist.x, wrist.y, current_time))
                        # Keep only the last 0.4 seconds of history
                        swipe_history = [pt for pt in swipe_history if current_time - pt[2] <= 0.4]

                        if len(swipe_history) >= 2:
                            # Compare newest to oldest
                            oldest = swipe_history[0]
                            newest = swipe_history[-1]
                            
                            dx = newest[0] - oldest[0]
                            dy = newest[1] - oldest[1]

                            # Thresholds (percentage of screen essentially, since coords are 0 to 1)
                            # E.g., moving 15% of the frame width in 0.4s
                            SWIPE_THRESHOLD = 0.15
                            
                            if abs(dx) > SWIPE_THRESHOLD or abs(dy) > SWIPE_THRESHOLD:
                                swipe_direction = None
                                if abs(dx) > abs(dy):
                                    # Horizontal
                                    if dx < 0:
                                        swipe_direction = "SwipeLeft"
                                    else:
                                        swipe_direction = "SwipeRight"
                                else:
                                    # Vertical
                                    if dy < 0:
                                        swipe_direction = "SwipeUp"
                                    else:
                                        swipe_direction = "SwipeDown"
                                
                                if swipe_direction:
                                    log_msg(f"[INFO] Detected dynamic gesture: {swipe_direction}")
                                    action_to_exec = swipe_config.get(swipe_direction)
                                    if action_to_exec:
                                        execute_action(action_to_exec)
                                    swipe_history.clear()
                                    swipe_cooldown_until = current_time + 1.0 # 1 second cooldown between swipes
                else:
                    swipe_history.clear()

                if prev_x == 0 and prev_y == 0:
                    cursor_x = raw_x
                    cursor_y = raw_y
                else:
                    cursor_x = prev_x * smoothing_factor + raw_x * (1 - smoothing_factor)
                    cursor_y = prev_y * smoothing_factor + raw_y * (1 - smoothing_factor)
                
                prev_x, prev_y = cursor_x, cursor_y

                cursor_x = max(0, min(screen_w - 1, cursor_x))
                cursor_y = max(0, min(screen_h - 1, cursor_y))

                # The mouse ONLY moves if the hand is actively making the 'MoveMouse' gesture
                allow_mouse_move = False
                if active_continuous_action == "MoveMouse":
                    allow_mouse_move = True

                if allow_mouse_move and time.time() - last_action_time > 0.5:
                    pyautogui.moveTo(int(cursor_x), int(cursor_y))
                    dist = math.hypot(index_finger.x - thumb.x, index_finger.y - thumb.y)
                    if dist < 0.05:
                        log_msg("[ACTION] Click!")
                        pyautogui.click()
                        time.sleep(0.2)
                
                # Window Movement Logic
                import pygetwindow as gw
                if active_continuous_action == "MoveWindow":
                    if target_window is None:
                        try:
                            target_window = gw.getActiveWindow()
                            if target_window is not None:
                                start_hand_x = cursor_x
                                start_hand_y = cursor_y
                                start_win_x, start_win_y = target_window.topleft
                        except Exception as e:
                            log_msg(f"[ERROR] Failed to get active window: {e}")
                    elif target_window is not None:
                        # Move the window relative to hand movement (amplified by 1.5x for easier dragging)
                        dx = (cursor_x - start_hand_x) * 1.5
                        dy = (cursor_y - start_hand_y) * 1.5
                        try:
                            target_window.moveTo(int(start_win_x + dx), int(start_win_y + dy))
                        except Exception as e:
                            log_msg(f"[ERROR] Failed to move window: {e}")
                else:
                    target_window = None
                
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS)

        cv2.imshow('Gesture OS - Camera Feed', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.01)

    cap.release()
    cv2.destroyAllWindows()
    log_msg("[INFO] Hand Motion controller stopped.")

except Exception as e:
    log_msg(f"[FATAL ERROR] {e}")
    import traceback
    log_msg(traceback.format_exc())
    sys.exit(1)


