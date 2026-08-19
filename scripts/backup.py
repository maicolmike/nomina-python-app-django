#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backup.py -> hace una copia de seguridad de la base de datos.

Funciona igual en tu PC y en PythonAnywhere. Usa la copia por SQLite, así que
es segura incluso si la app está abierta (incluye los cambios pendientes del
modo WAL).

Uso:
    python scripts/backup.py

Crea el archivo backup_nomina_AAAAMMDD_HHMM.db en la carpeta "backups" del
proyecto (junto a static/). Para restaurarlo: copia ese archivo como nomina.db
en la raíz del proyecto (y recarga la web).
"""
import os
import sqlite3
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROYECTO_DIR = os.path.dirname(SCRIPT_DIR)
BACKUP_DIR = os.path.join(PROYECTO_DIR, "backups")

# La base de datos puede estar en otro lugar (variable NOMINA_DB). En ese caso
# la carpeta de la base es la que manda; si no, usamos la de la raíz del proyecto.
if os.environ.get("NOMINA_DB"):
    DB_PATH = os.environ["NOMINA_DB"]
    BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "backups")
else:
    DB_PATH = os.path.join(PROYECTO_DIR, "nomina.db")


def main():
    if not os.path.exists(DB_PATH):
        print(f"No existe la base de datos: {DB_PATH}")
        sys.exit(1)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    destino = os.path.join(BACKUP_DIR, f"backup_nomina_{fecha}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(destino)
    src.backup(dst)
    dst.close()
    src.close()
    print(f"Backup creado: {destino}")


if __name__ == "__main__":
    main()