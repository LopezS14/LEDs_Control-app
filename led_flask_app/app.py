import os
import time
import threading

import cv2
import imutils
from flask import Flask, render_template, Response, request, jsonify

import serial
import serial.tools.list_ports


# ===================== Control de LEDs vía puerto serie =====================

class LedControllerSerial:
    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.lock = threading.Lock()

    def _auto_detect_port(self):
        puertos = list(serial.tools.list_ports.comports())
        if not puertos:
            raise RuntimeError("No se encontraron puertos serie.")
        return puertos[0].device

    def list_ports(self):
        puertos = list(serial.tools.list_ports.comports())
        return [{"device": p.device, "description": p.description} for p in puertos]

    def connect(self, port=None):
        with self.lock:
            if self.ser is not None and self.ser.is_open:
                return

            if port:
                self.port = port

            if self.port is None:
                self.port = self._auto_detect_port()

            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.2)
            time.sleep(0.7)

    def disconnect(self):
        with self.lock:
            if self.ser is not None:
                try:
                    self.ser.close()
                finally:
                    self.ser = None

    def is_connected(self):
        with self.lock:
            return self.ser is not None and self.ser.is_open

    def _send_command_byte(self, value: int):
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("No hay conexión serie activa.")
        if not (0 <= value <= 255):
            raise ValueError("Comando fuera de rango (0..255).")
        self.ser.write(bytes([value]))

    def set_led(self, modo: str):
        mapping = {
            "blanco": 8,
            "uv": 7,
            "violeta": 9,
            "azul": 10,
        }
        if modo not in mapping:
            raise ValueError("Modo inválido.")
        cmd = mapping[modo]
        with self.lock:
            self._send_command_byte(cmd)
        return cmd

    def set_intensity(self, nivel: int, retries: int = 4, delay: float = 0.12):
        if not (0 <= nivel <= 5):
            raise ValueError("Nivel fuera de rango 0..5.")
        cmd = 11 if nivel == 0 else nivel + 1
        with self.lock:
            for _ in range(retries):
                self._send_command_byte(cmd)
                time.sleep(delay)
        return cmd


# ===================== Cámara =====================

class CameraManager:
    def __init__(self):
        self.cap = None
        self.running = False
        self.last_frame = None
        self.lock = threading.Lock()

    def start(self, cam_idx, backend=None):
        self.stop()
        cap = cv2.VideoCapture(cam_idx, backend) if backend else cv2.VideoCapture(cam_idx)
        if not cap.isOpened():
            return False

        self.cap = cap
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        self.cap = None
        self.last_frame = None

    def _loop(self):
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.last_frame = frame
            time.sleep(0.01)

    def get_jpeg(self, width=1280):
        with self.lock:
            frame = None if self.last_frame is None else self.last_frame.copy()

        if frame is None:
            return None

        frame = imutils.resize(frame, width=width)
        ok, jpg = cv2.imencode(".jpg", frame)
        return jpg.tobytes() if ok else None

    def save_series(self, path, n):
        os.makedirs(path, exist_ok=True)
        for i in range(n):
            with self.lock:
                frame = None if self.last_frame is None else self.last_frame.copy()
            if frame is None:
                time.sleep(0.05)
                continue
            frame = imutils.resize(frame, width=1280)
            cv2.imwrite(os.path.join(path, f"captura_{i}.jpg"), frame)
            time.sleep(0.03)


# ===================== Flask =====================

app = Flask(__name__)

ctrl = LedControllerSerial()
cam = CameraManager()

LED_TO_FOLDER = {
    "blanco": "Luzblanca",
    "uv": "365nm",
    "violeta": "405nm",
    "azul": "455nm",
}

DEFAULT_BACKEND = cv2.CAP_DSHOW  # cambia a None o CAP_MSMF si falla


@app.get("/")
def index():
    return render_template("index.html")


# ---------- SERIAL ----------

@app.get("/api/serial/ports")
def serial_ports():
    return jsonify({"ports": ctrl.list_ports()})

@app.post("/api/serial/connect")
def serial_connect():
    data = request.get_json(silent=True) or {}
    ctrl.connect(port=data.get("port"))
    return jsonify({"port": ctrl.port})

@app.post("/api/serial/disconnect")
def serial_disconnect():
    ctrl.disconnect()
    return jsonify({"ok": True})


# ---------- LED ----------

@app.post("/api/led/mode")
def led_mode():
    data = request.get_json(force=True)
    cmd = ctrl.set_led(data["mode"])
    return jsonify({"cmd": cmd})

@app.post("/api/led/intensity")
def led_intensity():
    data = request.get_json(force=True)
    cmd = ctrl.set_intensity(int(data["level"]))
    return jsonify({"cmd": cmd})


# ---------- CÁMARA ----------

@app.post("/api/camera/start")
def camera_start():
    idx = int(request.get_json(force=True).get("index", 0))
    if not cam.start(idx, backend=DEFAULT_BACKEND):
        cam.start(idx, backend=None)
    return jsonify({"ok": True})

@app.post("/api/camera/stop")
def camera_stop():
    cam.stop()
    return jsonify({"ok": True})

@app.get("/video_feed")
def video_feed():
    def gen():
        while True:
            jpg = cam.get_jpeg()
            if jpg:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(0.03)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ---------- CAPTURA (CARPETA DINÁMICA) ----------

@app.post("/api/capture/series")
def capture_series():
    data = request.get_json(force=True)

    n = int(data.get("n_images", 25))
    led_mode = data.get("mode", "blanco")
    intensity = int(data.get("intensity", 0))

    folder_name = data.get("folder", "Sesion_01")

    carpeta_led = LED_TO_FOLDER.get(led_mode, "Desconocido")
    ruta = os.path.join(folder_name, carpeta_led, f"intensidad_{intensity}")

    if not cam.running:
        return jsonify({"error": "La cámara no está activa"}), 400

    # CLAVE: crear directorios antes de guardar
    os.makedirs(ruta, exist_ok=True)

    threading.Thread(target=cam.save_series, args=(ruta, n), daemon=True).start()

    return jsonify({"ok": True, "path": ruta, "n_images": n})



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
