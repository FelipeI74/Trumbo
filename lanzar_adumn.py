import uvicorn
import webbrowser
import threading
import time
import os
import sys
from datetime import date

# --- FECHA DE EXPIRACIÓN DEL BETA ---
# El 10 de Noviembre de 2026
FECHA_LIMITE = date(2026, 11, 10) 
# -------------------------------------

if getattr(sys, 'frozen', False):
    # Si estamos dentro del .exe, la carpeta de trabajo es la carpeta del .exe
    os.chdir(os.path.dirname(sys.executable))
else:
    # Si estamos en desarrollo, la carpeta de trabajo es la actual
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

def abrir_navegador():
    # Espera 2 segundos para que el servidor arranque
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    FECHA_LIMITE = date(2026, 12, 31)  # Margen amplio para el beta

    if date.today() > FECHA_LIMITE:
        print("========================================")
        print("   EL PERIODO DE PRUEBA HA EXPIRADO.")
        print("   Contacta con el equipo de ADUMN para renovar tu licencia.")
        print("========================================")
        time.sleep(10)
        sys.exit(0)

    print("Iniciando ADUMN Beta...")
    print("El navegador se abrira automaticamente.")
    print("No cierres esta ventana mientras uses ADUMN.")

    threading.Thread(target=abrir_navegador, daemon=True).start()

    # FIX CRÍTICO: Importar la app directamente (no como string)
    from app.main import app as adumn_app
    uvicorn.run(adumn_app, host="127.0.0.1", port=8000)
