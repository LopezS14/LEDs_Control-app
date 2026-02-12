# LED Flask App

## Ejecutar (Windows)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abrir: http://127.0.0.1:5000

## Notas
- Si la cámara no abre, edita `DEFAULT_BACKEND` en `app.py` y pon `None` o prueba `cv2.CAP_MSMF`.
