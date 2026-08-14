#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backup.py -> hace una copia de seguridad de la base de datos.

Funciona igual en tu PC y en PythonAnywhere (correrlo desde la carpeta del
proyecto). Usa la copia por SQLite, así que es segura incluso si la app está
abierta (incluye los cambios pendientes del modo WAL).

Uso:
    python backup.py

Crea el archivo backup_nomina_AAAAMMDD_HHMM.db en la misma carpeta.
Para restaurarlo: copia ese archivo como nomina.db (y recarga la web).
"""
import os
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("NOMINA_DB", os.path.join(BASE_DIR, "nomina.db"))


def main():
    if not os.path.exists(DB_PATH):
        print(f"No existe la base de datos: {DB_PATH}")
        sys.exit(1)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    destino = os.path.join(os.path.dirname(DB_PATH), f"backup_nomina_{fecha}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(destino)
    src.backup(dst)
    dst.close()
    src.close()
    print(f"Backup creado: {destino}")


if __name__ == "__main__":
    main()