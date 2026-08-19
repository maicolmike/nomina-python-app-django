#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""restablecer.py -> borra la base y recarga la información inicial.

Advertencia: ESTO BORRA TODO lo que haya en la base actual (nóminas, multas,
jugadores agregados, config...) y la vuelve a crear con los datos de ejemplo
(PARTICIPANTES_SEED, MULTAS_SEED y la configuración por defecto).

Antes de ejecutarlo, conviene correr primero:  python scripts/backup.py

Uso:
    python scripts/restablecer.py

Te pedirá escribir BORRAR para confirmar.
En PythonAnywhere: después de ejecutarlo, pulsa Reload en la pestaña Web
para que el sitio abra la base nueva.
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROYECTO_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.environ.get("NOMINA_DB", os.path.join(PROYECTO_DIR, "nomina.db"))


def main():
    print("Esto BORRA la base actual y recarga la información inicial")
    print(f"  Archivo: {DB_PATH}")
    resp = input("¿Escribir BORRAR para confirmar? ").strip()
    if resp != "BORRAR":
        print("Cancelado.")
        return
    for sufijo in ("", "-wal", "-shm"):
        ruta = DB_PATH + sufijo
        if os.path.exists(ruta):
            os.remove(ruta)
            print(f"Borrado: {ruta}")
    sys.path.insert(0, PROYECTO_DIR)
    import app as servidor
    servidor.init_db()
    print("Base restablecida con la información inicial.")
    print("En PythonAnywhere: pulsa Reload en la pestaña Web para usar la base nueva.")


if __name__ == "__main__":
    main()