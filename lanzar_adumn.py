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
    # Comprobar la fecha antes de hacer nada
    if date.today() > FECHA_LIMITE:
        print("========================================")
        print("   EL PERIODO DE PRUEBA HA EXPIRADO.")
        print("   Gracias por usar ADUMN Beta.")
        print("   Tus datos estan guardados en la carpeta del programa.")
        print("========================================")
        time.sleep(10) # Espera 10 segundos antes de cerrarse
        sys.exit(0) # Cierra el programa

    print("Iniciando ADUMN Beta...")
    print("El navegador se abrirá automáticamente.")
    print("No cierres esta ventana negra mientras uses ADUMN.")
    
    # Abre el navegador en un hilo aparte
    threading.Thread(target=abrir_navegador, daemon=True).start()
    
    # Arranca el servidor ADUMN
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)