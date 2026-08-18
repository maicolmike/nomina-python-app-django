#!/usr/bin/env python3
"""Nomina de jugadores - FAMILIA MIXTO SIN LIMITES 2023.

App web sin dependencias externas (solo Python 3.8+ y SQLite).
Ejecutar:  python3 app.py     ->  http://localhost:8000
"""

# =============================================================================
# IMPORTS (librerías que usa el proyecto)
# -----------------------------------------------------------------------------
# Solo usamos librerías que vienen con Python (no hay que instalar nada extra).
import json          # para leer/escribir datos en formato JSON (la API)
import os            # rutas de archivos (donde está la base de datos, la carpeta static...)
import re            # expresiones regulares, para buscar patrones en textos
import secrets       # genera tokens aleatorios y seguros para las sesiones de la directiva
import sqlite3       # la base de datos (guardar jugadores, multas, nómina...)
import threading     # permite que el servidor atienda varias peticiones a la vez
import unicodedata   # quita tildes a los nombres (para buscar mejor)
from datetime import date, datetime, timedelta, time  # manejo de fechas y horas
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # el servidor web
from urllib.parse import parse_qs, urlparse  # analizar las rutas y parámetros de las URLs

# =============================================================================
# RUTAS Y CONFIGURACIÓN BÁSICA
# -----------------------------------------------------------------------------
# BASE_DIR  -> carpeta donde vive este archivo (la raíz del proyecto)
# STATIC_DIR-> carpeta "static" donde están el HTML, CSS y JavaScript de la interfaz
# DB_PATH   -> archivo SQLite con los datos. Se puede cambiar con la variable
#              de entorno NOMINA_DB (útil para probar sin tocar los datos reales)
# PORT      -> puerto donde escucha el servidor (8000 por defecto)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.environ.get("NOMINA_DB", os.path.join(BASE_DIR, "nomina.db"))
PORT = int(os.environ.get("NOMINA_PORT", "8000"))

# Así se maneja la base para que varias personas puedan trabajar a la vez (hasta ~5):
#   - Cada petición abre su PROPIA conexión SQLite y la cierra al terminar; así los
#     hilos/procesos ya no comparten una misma conexión (esa era la causa de conflictos).
#   - El modo WAL (Write-Ahead Logging) permite que muchos lean mientras uno escribe.
#   - Las escrituras van en fila con un candado (_escribir_lock) para que dos personas
#     no modifiquen el mismo dato exactamente a la vez ni se superen los cupos.
#   - Las sesiones de la directiva se guardan EN LA BASE (tabla "sesiones"), no en memoria,
#     para que sobrevivan reinicios y a varios procesos.
_escribir_lock = threading.RLock()

# =============================================================================
# VALORES INICIALES (se guardan en la base la primera vez que se ejecuta)
# -----------------------------------------------------------------------------
# REGLAS_DEFAULT -> el texto de las reglas del grupo que se muestra en la nómina
# REGLAMENTO_MULTAS_DEFAULT -> las reglas sobre multas (cuánto, plazos, etc.)
REGLAS_DEFAULT = """1. Prioridad solo se anotarán integrantes del grupo oficial. El cupo es 6 mujeres y 6 hombres, se respetará los cupos por género.
2. Corte de nómina será 9:00 am, después de esa hora se podrá anotar a personas fuera del grupo, tambien de ser necesario no se tomará en cuenta los cupos por género la idea es llenar la nómina siempre y cuando no haya lista de espera.
3. Si después del corte de nómina, hay lista de espera y en la nómina hay 1 cupo para mujer, entra una mujer de la lista de espera, aunque no sea la primera en la lista y viceversa en el caso de cupo para los hombres, Si no hay nadie del mismo género en espera, Entra la primera persona de la lista, sin importar género."""

REGLAMENTO_MULTAS_DEFAULT = """1. Plazo maximo para pagar multas son 15 dias apartir de la fecha de multa.
2. Si alguien por algún motivo se hace sacar del grupo por estar debiendo multa, el ingreso nuevamente cuesta $10.000.
3. Compañer@ que llegó con anticipación no se alistó, no fue al baño etc. Empezó la hora del partido y no ha ingresado a la cancha, multa de $1000 pesos.
4. La puntualidad de llegada es hora de reloj de mano, si llega con un minuto de retraso a la cancha según hora indicada. Ejemplo 5:01pm la multa será de $2000.
5. La no asistencia cuesta $10.000, los que no estén dentro de nuestro grupo, se cobrará al que lo apunto.
6. Si sale bravo o se sale antes de acabar el juego cuesta $5000.
7. Multa por agresión cuesta $20.000.
8. Para cancelar cancha valido hasta las 12m si cancela de la 1 pm en adelante debe buscar remplazo o contactar y asegurarse asista el primero de lista de espera si lo hay.
9. Multa $20.000 para el jugador que incurre en falta cometida que implique contacto físico o lesión. Después de 3 para volver al grupo."""

# MOTIVOS_MULTA -> los motivos fijos de multa (los de siempre). Cada uno tiene
# una "clave" (nombre interno) y el texto que ve la directiva en pantalla.
MOTIVOS_MULTA = [
    ("multa_tarde", "Llegó tarde (regla 4)"),
    ("multa_no_alisto", "No se alistó / no entró a la cancha (regla 3)"),
    ("multa_no_asistio", "No asistió (regla 5)"),
    ("multa_salio", "Salió bravo o antes de terminar (regla 6)"),
    ("multa_agresion", "Agresión (regla 7)"),
    ("multa_falta", "Falta con contacto físico o lesión (regla 9)"),
    ("multa_reingreso", "Reingreso al grupo (regla 2)"),
]

# CONFIG_DEFAULT -> configuración inicial del grupo. Estos valores se guardan
# en la tabla "config" y luego la directiva puede cambiarlos desde la interfaz.
# Se pueden sobrescribir con variables de entorno (NOMINA_PIN, por ejemplo).
CONFIG_DEFAULT = {
    "nombre_grupo": "FAMILIA MIXTO SIN LÍMITES 2023 ❤️",
    "cancha": "Coliseo las Américas",
    "dia": "Domingo",
    "hora": "16:50",
    "cupos_mujeres": "6",
    "cupos_hombres": "6",
    "cupos_personalizados": "0",
    "plazo_dias": "15",
    "multa_tarde": "2000",
    "multa_no_alisto": "1000",
    "multa_no_asistio": "10000",
    "multa_salio": "5000",
    "multa_agresion": "20000",
    "multa_falta": "20000",
    "multa_reingreso": "10000",
    "pin": os.environ.get("NOMINA_PIN", "2023"),
    "hora_corte_invitados": "09:00",
    "reglas": REGLAS_DEFAULT,
    "reglamento_multas": REGLAMENTO_MULTAS_DEFAULT,
    "emoji_f": "🌹",
    "emoji_m": "⚽",
}

# PARTICIPANTES_SEED -> lista de jugadores que se crean la primera vez.
# Cada fila es: (nombre, genero, es_miembro, activo, expulsado).
# Los marcados como "expulsado" se guardan solo para conservar su historial.
PARTICIPANTES_SEED = [
    # (nombre, genero, miembro, activo, expulsado)
    ("Adriana Nastacuaz", "F", 1, 1, 0), ("Amparo Quinchoa", "F", 1, 1, 0),
    ("Claudia Evanjuanoy", "F", 1, 1, 0), ("Deisy Evanjuanoy", "F", 1, 1, 0),
    ("Edilma", "F", 1, 1, 0), ("Gabriella", "F", 1, 1, 0),
    ("Jennifer Mora", "F", 1, 1, 0), ("Jenny Beltran", "F", 1, 1, 0),
    ("Leibi Yojana", "F", 1, 1, 0), ("Lucely Rosero", "F", 1, 1, 0),
    ("Lucia Vargas", "F", 1, 1, 0), ("Luz Giraldo", "F", 1, 1, 0),
    ("Mariana Mera", "F", 1, 1, 0), ("Michell", "F", 1, 1, 0),
    ("Monica Ordoñez", "F", 1, 1, 0), ("Nancy Gomez", "F", 1, 1, 0),
    ("Nathalia De La Cruz", "F", 1, 1, 0), ("Paola Chaves", "F", 1, 1, 0),
    ("Patricia Ordoñez", "F", 1, 1, 0), ("Raisa Milady Rueda", "F", 1, 1, 0),
    ("Sandra Nupan", "F", 1, 1, 0), ("Shirley", "F", 1, 1, 0),
    ("Socorro Cruz", "F", 1, 1, 0), ("Stefany Diaz Moncayo", "F", 1, 1, 0),
    ("Yolanda Hoyos", "F", 1, 1, 0), ("Yuly Fernanda Chaves Acosta", "F", 1, 1, 0),
    ("Alejandro Hernandez", "M", 1, 1, 0), ("Cristian Meneses", "M", 1, 1, 0),
    ("Dario Chapal", "M", 1, 1, 0), ("Dario Rodriguez", "M", 1, 1, 0),
    ("Dario Toro", "M", 1, 1, 0), ("David Papamija", "M", 1, 1, 0),
    ("David Valencia", "M", 1, 1, 0), ("Eider Gaviria", "M", 1, 1, 0),
    ("Eyder Iles", "M", 1, 1, 0), ("Fabian Ñañez", "M", 1, 1, 0),
    ("Guillermo Piedrahita", "M", 1, 1, 0), ("Guillermo Solarte", "M", 1, 1, 0),
    ("Jeiler Biyey", "M", 1, 1, 0), ("Joe Ortiz", "M", 1, 1, 0),
    ("Juan Chavez", "M", 1, 1, 0), ("Kevin Galarraga", "M", 1, 1, 0),
    ("Lizandro Escobar", "M", 1, 1, 0), ("Maicol Yela", "M", 1, 1, 0),
    ("Marlon Benavides", "M", 1, 1, 0),
    ("Mauricio Pejendino", "M", 1, 1, 0), ("Orlando Muñoz", "M", 1, 1, 0),
    ("Ramiro Solarte Perez", "M", 1, 1, 0),
    # --- Reportados por multas (se conservan para no perder su historial) ---
    ("Jiménez", "M", 1, 0, 1), ("Erika", "F", 1, 0, 1), ("Mauricio Hidalgo", "M", 1, 0, 1),
    ("Alejandro Medina", "M", 1, 0, 1), ("Maira Perdomo", "F", 1, 0, 1),
    ("Jeider Narváez", "M", 1, 0, 1), ("Alejandro Arciniegas", "M", 1, 0, 1),
    ("Giovany Pachanjoa", "M", 1, 1, 0), ("Juan S", "M", 1, 1, 0),
    ("Lorain Futbol", "F", 1, 1, 0), ("Mary Ordoñez", "F", 1, 1, 0),
    ("SANTA", "M", 1, 1, 0),
]

NOMINA_SEED = []

# MULTAS_SEED -> multas ya existentes que se cargan la primera vez.
# A las que no tienen plazo (""), se les calcula uno sumando el plazo por defecto.
MULTAS_SEED = [
    # (nombre, fecha, valor, abono, plazo_max) -- LISTADO DE MULTAS
    ("Deisy Evanjuanoy", "2026-08-08", 2000, 0, "2026-09-08"),
    ("Dario Rodriguez", "2026-08-09", 6000, 0, "2026-09-09"),
    # ELIMINADOS POR NO PAGAR MULTAS
    ("Jiménez", "2025-04-22", 8000, 0, "2025-05-07"), ("Jiménez", "2025-04-22", 8000, 0, "2025-05-07"),
    ("Erika", "2025-06-21", 2000, 0, "2025-07-06"), ("Erika", "2025-06-26", 80000, 0, "2025-07-11"),
    ("Mauricio Hidalgo", "2026-03-28", 2000, 0, "2026-04-12"),
    ("Mauricio Hidalgo", "2026-03-28", 2000, 0, "2026-04-12"),
    ("Alejandro Medina", "2026-06-08", 10000, 0, "2026-06-23"),
    ("Maira Perdomo", "2026-06-06", 2000, 0, "2026-06-21"),
    ("Jeider Narváez", "2026-06-06", 2000, 0, "2026-06-21"),
    ("Alejandro Arciniegas", "2026-06-18", 10000, 7000, "2026-07-03"),
]

# SCHEMA -> las tablas de la base de datos SQLite.
#  - config:       los valores de configuración del grupo (clave/valor)
#  - participantes: los jugadores (ficha completa de cada uno)
#  - partidos:     los partidos/encuentros (fecha, hora, cancha, estado...)
#  - nomina:       quién está anotado en cada partido (nómina o lista de espera).
#                  Un invitado sin ficha se guarda con nombre_libre/genero_libre.
#  - multas:       las multas de cada jugador (valor, abonos, plazo, estado)
#  - motivos_multa: motivos de multa personalizados que agrega la directiva
SCHEMA = """
CREATE TABLE IF NOT EXISTS config (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS participantes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE,
  genero TEXT NOT NULL CHECK (genero IN ('F','M')),
  miembro INTEGER NOT NULL DEFAULT 1,
  activo INTEGER NOT NULL DEFAULT 1,
  expulsado INTEGER NOT NULL DEFAULT 0,
  telefono TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS partidos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL,
  hora TEXT NOT NULL,
  cancha TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'abierta',
  activo INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nomina (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
  participante_id INTEGER REFERENCES participantes(id) ON DELETE CASCADE,
  lista TEXT NOT NULL CHECK (lista IN ('nomina','espera')),
  invitado_por TEXT DEFAULT '',
  nombre_libre TEXT DEFAULT '',
  genero_libre TEXT DEFAULT '',
  creado TEXT NOT NULL,
  UNIQUE (partido_id, participante_id)
);
CREATE TABLE IF NOT EXISTS multas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  participante_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  fecha TEXT NOT NULL,
  valor INTEGER NOT NULL,
  abono INTEGER NOT NULL DEFAULT 0,
  motivo TEXT DEFAULT '',
  plazo TEXT DEFAULT '',
  estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','pagada'))
);
CREATE TABLE IF NOT EXISTS motivos_multa (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  texto TEXT NOT NULL UNIQUE,
  valor INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sesiones (
  token TEXT PRIMARY KEY,
  rol TEXT NOT NULL DEFAULT 'directiva',
  nombre TEXT DEFAULT '',
  creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canchas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
"""

# Estructura general del proyecto:
# - El servidor usa Python estándar y SQLite para guardar la nómina, multas, partidos y configuración.
# - La interfaz web vive en la carpeta static y se comunica con este archivo a través de una API JSON.


# ErrorApp -> excepción propia de la app. Sirve para responder al navegador
# con un mensaje claro y un código HTTP (400 por defecto) en lugar de un error interno.
class ErrorApp(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


# ----------------------------------------------------------------------------
# FUNCIONES AUXILIARES
# ----------------------------------------------------------------------------

# normalizar("Mónica!") -> "monica". Quita tildes, mayúsculas y espacios extra.
# Se usa para buscar nombres sin importar cómo estén escritos.
def normalizar(texto):
    t = unicodedata.normalize("NFD", (texto or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


# fecha_es("2026-08-08") -> "08/08/2026". Solo cambia el formato para mostrarlo.
def fecha_es(fecha_iso):
    try:
        return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return fecha_iso or ""


# hora_es("16:50") -> "4:50pm". Convierte la hora a formato 12 horas para mostrarla.
def hora_es(hora):
    try:
        h, m = (int(x) for x in str(hora).split(":")[:2])
    except ValueError:
        return hora
    sufijo = "am" if h < 12 else "pm"
    return f"{(h % 12) or 12}:{m:02d}{sufijo}"


# -----------------------------------------------------------------------------
# ACCESO A LA BASE DE DATOS (seguro para varias personas a la vez)
# -----------------------------------------------------------------------------

def nueva_conexion():
    """Abre una conexión SQLite nueva y bien configurada.

    - timeout: si la base está ocupada por otro, espera hasta N segundos antes de fallar.
    - WAL: deja que muchos lean mientras uno escribe (clave del soporte multi-usuario).
    - foreign_keys: mantiene el borrado en cascada al quitar jugadores/partidos.
    """
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    con.execute("PRAGMA journal_mode = WAL")
    return con


class _ConexionLocal:
    """Objeto 'DB' virtual: CADA HILO usa su propia conexión SQLite.

    Todas las operaciones DB.execute/DB.commit de todo el proyecto pasan por
    aquí. Con threading.local, cada hilo/petición tiene una conexión aparte y
    nunca comparte esa conexión con otro hilo (la causa original de los
    errores "created in a thread can only be used in that same thread").
    """

    def __init__(self):
        self._local = threading.local()

    def _asignar(self, con):
        self._local.con = con

    def _cerrar(self):
        con = getattr(self._local, "con", None)
        if con is not None:
            try:
                con.close()
            finally:
                self._local.con = None

    def _actual(self):
        con = getattr(self._local, "con", None)
        if con is None:
            con = nueva_conexion()
            self._local.con = con
        return con

    def __getattr__(self, nombre):
        return getattr(self._actual(), nombre)


# DB -> acceso a la base. No es una conexión "global": cada hilo tiene la suya.
DB = _ConexionLocal()


class conexion_peticion:
    """Delimita UNA petición: abre una conexión nueva del hilo y la cierra al salir.

    Uso:
        with conexion_peticion(escribir=True):
            ...código que lee y escribe la base...

    - escribir=True   -> candado de escritura: dos personas no editan a la vez
                         (evita pasarse de cupos o pisarse cambios).
    - escribir=False  -> lectura normal: todas van en paralelo.
    """

    def __init__(self, escribir=False):
        self._escribir = escribir

    def __enter__(self):
        if self._escribir:
            _escribir_lock.acquire()
        try:
            DB._cerrar()                      # descarta la conexión vieja del hilo
            DB._asignar(nueva_conexion())
        except Exception:
            if self._escribir:
                _escribir_lock.release()
            raise
        return DB._actual()

    def __exit__(self, tipo, valor, tb):
        try:
            if tipo is not None:
                try:
                    DB._actual().rollback()
                except sqlite3.Error:
                    pass
        finally:
            try:
                DB._cerrar()
            finally:
                if self._escribir:
                    _escribir_lock.release()


# init_db(): prepara la base al arrancar.
#   1. Abre una conexión temporal y activa las claves foráneas.
#   2. Crea las tablas (SCHEMA) si no existen.
#   3. Aplica migraciones para bases viejas.
#   4. Guarda la configuración por defecto.
#   5. Si no hay jugadores, carga los datos iniciales (sembrar()).
def init_db():
    con = nueva_conexion()
    try:
        con.executescript(SCHEMA)
        migrar_nomina(con)
        migrar_partidos(con)
        migrar_canchas(con)
        for clave, valor in CONFIG_DEFAULT.items():
            con.execute("INSERT OR IGNORE INTO config (clave, valor) VALUES (?,?)", (clave, valor))
        if not con.execute("SELECT 1 FROM participantes LIMIT 1").fetchone():
            sembrar(con)
        con.commit()
    finally:
        con.close()


def migrar_nomina(con):
    """Agrega a la tabla nomina las columnas para invitados sin ficha de jugador.

    Un invitado que no está en la base se guarda directo en la nómina (nombre y
    género en texto), sin crear un participante. Solo aplica en bases viejas.
    """
    columnas = {r[1] for r in con.execute("PRAGMA table_info(nomina)")}
    if "nombre_libre" in columnas:
        return
    con.execute("ALTER TABLE nomina RENAME TO nomina_old")
    con.execute("""
      CREATE TABLE nomina (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partido_id INTEGER NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
        participante_id INTEGER REFERENCES participantes(id) ON DELETE CASCADE,
        lista TEXT NOT NULL CHECK (lista IN ('nomina','espera')),
        invitado_por TEXT DEFAULT '',
        nombre_libre TEXT DEFAULT '',
        genero_libre TEXT DEFAULT '',
        creado TEXT NOT NULL,
        UNIQUE (partido_id, participante_id)
      )
    """)
    con.execute("""
      INSERT INTO nomina (id, partido_id, participante_id, lista, invitado_por,
                          nombre_libre, genero_libre, creado)
      SELECT id, partido_id, participante_id, lista, invitado_por, '', '', creado
      FROM nomina_old
    """)
    con.execute("DROP TABLE nomina_old")
    con.commit()


def migrar_partidos(con):
    """Agrega la columna 'activo' a la tabla partidos en bases viejas.

    Marca cuál partido está 'en uso' (el que aparece en la nómina). Solo
    aplica en bases creadas antes de existir esa columna.
    """
    columnas = {r[1] for r in con.execute("PRAGMA table_info(partidos)")}
    if "activo" not in columnas:
        con.execute("ALTER TABLE partidos ADD COLUMN activo INTEGER NOT NULL DEFAULT 0")
        con.commit()


def migrar_canchas(con):
    """Llena la tabla de canchas con las que ya se usaron en partidos.

    La primera vez que corre una base existente, toma las canchas distintas de
    la tabla partidos y las guarda en "canchas", para que salgan en el
    autocompletado del formulario de partidos.
    """
    if not con.execute("SELECT 1 FROM canchas LIMIT 1").fetchone():
        con.execute(
            "INSERT OR IGNORE INTO canchas (nombre)"
            " SELECT DISTINCT cancha FROM partidos WHERE TRIM(cancha) != ''")
        con.commit()


# sembrar(con): llena la base con los jugadores y multas iniciales (solo la primera vez).
def sembrar(con):
    con.executemany(
        "INSERT OR IGNORE INTO participantes (nombre, genero, miembro, activo, expulsado)"
        " VALUES (?,?,?,?,?)",
        [(n, g, m, a, e) for n, g, m, a, e in PARTICIPANTES_SEED],
    )
    plazo = int(CONFIG_DEFAULT["plazo_dias"])
    for nombre, fecha, valor, abono, plazo_max in MULTAS_SEED:
        pid = id_por_nombre(nombre, con)
        if not pid:
            continue
        con.execute(
            "INSERT INTO multas (participante_id, fecha, valor, abono, plazo) VALUES (?,?,?,?,?)",
            (pid, fecha, valor, abono, plazo_max or sumar_dias(fecha, plazo)),
        )


def proximo_jueves():
    hoy = date.today()
    return (hoy + timedelta(days=(3 - hoy.weekday()) % 7)).isoformat()


# DIAS_SEMANA -> convierte el nombre del día (ej. "domingo") a su número,
# (0=lunes...6=domingo). Se usa para saber cuándo es el próximo día de juego.
DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def proximo_dia():
    """Próximo día de juego según la configuración ('dia'), o próximo jueves si no se reconoce."""
    nombre = normalizar(cfg()["dia"])
    objetivo = DIAS_SEMANA.get(nombre, 3)
    hoy = date.today()
    return (hoy + timedelta(days=(objetivo - hoy.weekday()) % 7 or 7)).isoformat()


# DIAS_NOMBRE -> lista de nombres de días de la semana en español.
DIAS_NOMBRE = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def dia_semana(fecha_iso):
    """Devuelve el día de la semana en español de la fecha del partido."""
    try:
        return DIAS_NOMBRE[datetime.strptime(fecha_iso, "%Y-%m-%d").weekday()]
    except (ValueError, TypeError):
        return ""


# sumar_dias("2026-08-08", 15) -> "2026-08-23". Suma días a una fecha (para el plazo).
def sumar_dias(fecha_iso, dias):
    try:
        return (datetime.strptime(fecha_iso, "%Y-%m-%d").date() + timedelta(days=dias)).isoformat()
    except (ValueError, TypeError):
        return ""


# id_por_nombre("Pedro", con) -> el id del participante, o None si no existe.
def id_por_nombre(nombre, con=None):
    con = con or DB
    fila = con.execute("SELECT id FROM participantes WHERE nombre = ?", (nombre,)).fetchone()
    return fila["id"] if fila else None


# cfg(): lee toda la tabla "config" y la devuelve como diccionario.
# Regla del proyecto: los cupos son 6/6 por defecto; si la directiva no activó
# los cupos personalizados, se ignoran otros valores que haya en la base.
def cfg():
    c = {r["clave"]: r["valor"] for r in DB.execute("SELECT clave, valor FROM config")}
    # El proyecto usa 6/6 por defecto. Si la directiva no guardó cupos personalizados,
    # cualquier valor viejo que siga en la base de datos debe ignorarse para no romper la regla.
    if str(c.get("cupos_personalizados", "0")).strip() != "1":
        c["cupos_mujeres"] = "6"
        c["cupos_hombres"] = "6"
    return c


# ----------------------------------------------------------------------------
# SESIONES DE LA DIRECTIVA (guardadas en la base, no en memoria)
# ----------------------------------------------------------------------------

def session_get(token):
    """Devuelve la sesión de un token, o None si no existe/expiró."""
    if not token:
        return None
    fila = DB.execute("SELECT rol, nombre FROM sesiones WHERE token = ?", (token,)).fetchone()
    if not fila:
        return None
    return {"rol": fila["rol"], "nombre": fila["nombre"]}


def session_set(token, datos):
    """Guarda una sesión nueva (login de la directiva)."""
    DB.execute(
        "INSERT OR REPLACE INTO sesiones (token, rol, nombre, creado) VALUES (?,?,?,?)",
        (token, datos.get("rol", "directiva"), datos.get("nombre") or "",
         datetime.now().isoformat(timespec="seconds")),
    )
    DB.commit()


def session_del(token):
    """Borra una sesión (logout)."""
    if token:
        DB.execute("DELETE FROM sesiones WHERE token = ?", (token,))
        DB.commit()


# entero("12") -> 12. Convierte a número entero; si falla, usa el valor "defecto".
def entero(valor, defecto=0):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


# cupo_por_genero(c, "F") -> cuántas mujeres caben en la nómina (6 si no hay
# cupos personalizados, o el valor de la config si sí los hay).
def cupo_por_genero(c, genero):
    personalizados = str(c.get("cupos_personalizados", "0")).strip() == "1"
    if not personalizados:
        return 6
    return entero(c["cupos_mujeres"], 6) if genero == "F" else entero(c["cupos_hombres"], 6)


# contar_en_nomina(partido_id, genero) -> cuántos hay anotados en la nómina
# de ese partido. Sin género cuenta todos; con género solo ese sexo.
def contar_en_nomina(partido_id, genero=None):
    if genero is None:
        fila = DB.execute(
            "SELECT COUNT(*) n FROM nomina n"
            " LEFT JOIN participantes p ON p.id = n.participante_id"
            " WHERE n.partido_id = ? AND n.lista = 'nomina'",
            (partido_id,),
        ).fetchone()
        return int(fila["n"] if fila else 0)
    fila = DB.execute(
        "SELECT COUNT(*) n FROM nomina n"
        " LEFT JOIN participantes p ON p.id = n.participante_id"
        " WHERE n.partido_id = ? AND n.lista = 'nomina'"
        " AND COALESCE(p.genero, n.genero_libre) = ?",
        (partido_id, genero),
    ).fetchone()
    return int(fila["n"] if fila else 0)


# puede_entrar_nomina(partido, genero, c) -> True si aún hay cupo para ese género.
def puede_entrar_nomina(partido_id, genero, c):
    return contar_en_nomina(partido_id, genero) < cupo_por_genero(c, genero)


def corte_invitados(partido):
    """Marca la hora del corte de invitados: las 9am del día del partido."""
    try:
        dia = datetime.strptime(partido["fecha"], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    hora = str(cfg().get("hora_corte_invitados") or "09:00").strip()
    try:
        h, m = (int(x) for x in hora.split(":")[:2])
        return datetime.combine(dia, time(h, m))
    except (ValueError, TypeError):
        return datetime.combine(dia, time(9, 0))


def permite_invitados(partido):
    """Los invitados solo entran a la nómina después del corte (9am del día del partido)."""
    corte = corte_invitados(partido)
    if corte is None:
        return True
    return datetime.now() >= corte


# crear_partido(fecha, hora, cancha, activo) -> guarda un partido nuevo y
# devuelve su id. Si "activo" es True, quita el estado "en uso" a los demás.
def crear_partido(fecha, hora, cancha, activo=False):
    if activo:
        DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
    # Si la cancha no está en la lista de canchas, se guarda sola (así aparece
    # en el autocompletado de los siguientes partidos).
    DB.execute("INSERT OR IGNORE INTO canchas (nombre) VALUES (?)", (cancha,))
    cur = DB.execute(
        "INSERT INTO partidos (fecha, hora, cancha, estado, activo, creado) VALUES (?,?,?,?,?,?)",
        (fecha, hora, cancha, "abierta", 1 if activo else 0,
         datetime.now().isoformat(timespec="seconds")),
    )
    DB.commit()
    return cur.lastrowid


def partido_actual():
    """Partido 'en uso' (el de la nómina). Por defecto se muestra el partido
    más antiguo, porque es el próximo a jugarse. Si ninguno está marcado,
    toma el más antiguo y lo marca como activo. No crea partidos nuevos:
    devuelve None si no hay ninguno."""
    fila = DB.execute("SELECT * FROM partidos WHERE activo = 1 LIMIT 1").fetchone()
    if not fila:
        fila = DB.execute(
            "SELECT * FROM partidos WHERE estado != 'cancelada' ORDER BY fecha ASC, id ASC LIMIT 1"
        ).fetchone()
        if fila:
            DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
            DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (fila["id"],))
            DB.commit()
            fila = DB.execute("SELECT * FROM partidos WHERE id = ?", (fila["id"],)).fetchone()
    if not fila:
        return None
    d = dict(fila)
    d["fecha_es"] = fecha_es(d["fecha"])
    d["hora_es"] = hora_es(d["hora"])
    return d


# anotados(partido_id) -> todos los registros de la nómina/espera de ese partido,
# incluyendo el nombre y género tanto de jugadores con ficha como invitados libres.
def anotados(partido_id):
    filas = DB.execute(
        "SELECT n.id, n.lista, n.invitado_por, n.nombre_libre, n.genero_libre, n.creado,"
        " p.id AS pid, p.nombre, p.genero, p.miembro, p.expulsado FROM nomina n"
        " LEFT JOIN participantes p ON p.id = n.participante_id"
        " WHERE n.partido_id = ? ORDER BY n.creado, n.id",
        (partido_id,),
    ).fetchall()
    salida = []
    for f in filas:
        d = dict(f)
        d["nombre"] = d["nombre"] or d["nombre_libre"]
        d["genero"] = d["genero"] or d["genero_libre"]
        d["miembro"] = 0 if d["miembro"] is None else d["miembro"]
        d["expulsado"] = 0 if d["expulsado"] is None else d["expulsado"]
        salida.append(d)
    return salida


# multas_lista() -> todas las multas con datos calculados: saldo (valor - abono),
# fecha y plazo formateados, si está vencida o no, y si el jugador fue expulsado.
def multas_lista():
    plazo_dias = entero(cfg()["plazo_dias"], 15)
    filas = DB.execute(
        "SELECT m.*, p.nombre, p.genero, p.expulsado FROM multas m JOIN participantes p"
        " ON p.id = m.participante_id ORDER BY p.nombre COLLATE NOCASE, m.fecha, m.id"
    ).fetchall()
    salida = []
    for f in filas:
        d = dict(f)
        d["saldo"] = max(0, d["valor"] - d["abono"])
        d["plazo"] = d["plazo"] or sumar_dias(d["fecha"], plazo_dias)
        d["fecha_es"] = fecha_es(d["fecha"])
        d["plazo_es"] = fecha_es(d["plazo"])
        d["expulsado"] = 1 if d.get("expulsado") else 0
        d["vencida"] = d["estado"] == "pendiente" and (d["plazo"] or "") < date.today().isoformat()
        salida.append(d)
    return salida


# jugadores_lista() -> todos los jugadores con su deuda pendiente total.
def jugadores_lista():
    deudas = {
        r["participante_id"]: r["deuda"] for r in DB.execute(
            "SELECT participante_id, SUM(valor - abono) deuda FROM multas"
            " WHERE estado = 'pendiente' GROUP BY participante_id")
    }
    salida = []
    for f in DB.execute("SELECT * FROM participantes ORDER BY nombre COLLATE NOCASE"):
        d = dict(f)
        d["deuda"] = max(0, deudas.get(d["id"], 0))
        salida.append(d)
    return salida


def motivos_personalizados():
    return [dict(f) for f in DB.execute(
        "SELECT * FROM motivos_multa ORDER BY texto COLLATE NOCASE")]


# partidos_lista() -> los partidos guardados con cuánta gente tienen anotada.
def partidos_lista():
    salida = []
    for f in DB.execute("SELECT * FROM partidos ORDER BY fecha ASC, id ASC LIMIT 60"):
        d = dict(f)
        d["fecha_es"] = fecha_es(d["fecha"])
        d["hora_es"] = hora_es(d["hora"])
        cuenta = DB.execute(
            "SELECT lista, COUNT(*) n FROM nomina WHERE partido_id = ? GROUP BY lista", (d["id"],)
        ).fetchall()
        conteos = {r["lista"]: r["n"] for r in cuenta}
        d["en_nomina"] = conteos.get("nomina", 0)
        d["en_espera"] = conteos.get("espera", 0)
        salida.append(d)
    return salida


# estado_completo(rol, partido_id) -> TODO lo que necesita la interfaz para
# pintar la pantalla: configuración, partido en uso, nómina, espera, cupos,
# multas, jugadores, partidos y el texto de WhatsApp. Es la petición
# más importante de la app (/api/estado).
def estado_completo(rol, partido_id=None):
    c = cfg()
    activo = partido_actual()
    partido = activo
    if partido_id:
        fila = DB.execute("SELECT * FROM partidos WHERE id = ? AND estado != 'cancelada'",
                          (partido_id,)).fetchone()
        if fila:
            d = dict(fila)
            d["fecha_es"] = fecha_es(d["fecha"])
            d["hora_es"] = hora_es(d["hora"])
            partido = d
    if partido:
        items = anotados(partido["id"])
        corte_info = {
            "permite": permite_invitados(partido),
            "fecha": partido["fecha"],
            "hora": c.get("hora_corte_invitados") or "09:00",
            "texto": ("Invitad@s ya pueden entrar a la nómina." if permite_invitados(partido)
                      else "Solo el grupo puede anotarse hasta el corte de invitad@s (9am del día del partido)."),
        }
    else:
        items = []
        corte_info = {
            "permite": False,
            "fecha": "",
            "hora": c.get("hora_corte_invitados") or "09:00",
            "texto": "No hay partido en uso. Crea uno o usa un partido guardado desde la pestaña Partidos.",
        }
    nomina = [i for i in items if i["lista"] == "nomina"]
    espera = [i for i in items if i["lista"] == "espera"]
    cupos_f, cupos_m = cupo_por_genero(c, "F"), cupo_por_genero(c, "M")
    multas = multas_lista()
    pendientes = [m for m in multas if m["estado"] == "pendiente"]
    return {
        "rol": rol,
        "requiere_pin": bool(c["pin"].strip()),
        "config": {k: c[k] for k in CONFIG_DEFAULT if k != "pin"},
        "motivos_multa": [
            {"clave": k, "texto": t, "valor": entero(c.get(k), 0), "personalizado": False}
            for k, t in MOTIVOS_MULTA
        ] + [
            {"clave": None, "id": m["id"], "texto": m["texto"], "valor": m["valor"],
             "personalizado": True}
            for m in motivos_personalizados()
        ],
        "partido": partido,
        "partido_vista_id": partido["id"] if partido else None,
        "partido_activo_id": activo["id"] if activo else None,
        "corte_invitados": corte_info,
        "nomina": nomina,
        "espera": espera,
        "cupos": {
            "mujeres": cupos_f, "hombres": cupos_m,
            "usadas_f": sum(1 for i in nomina if i["genero"] == "F"),
            "usadas_m": sum(1 for i in nomina if i["genero"] == "M"),
        },
        "multas": multas,
        "resumen_multas": {
            "deuda": sum(m["saldo"] for m in pendientes),
            "vencidas": sum(1 for m in pendientes if m["vencida"]),
            "pendientes": len(pendientes),
        },
        "jugadores": jugadores_lista(),
        "partidos": partidos_lista(),
        "canchas": canchas_lista("", 200),
        "texto": texto_whatsapp(partido),
    }


# texto_whatsapp(partido) -> arma el mensaje completo que se copia a WhatsApp:
# encabezado, nómina numerada, lista de espera, multas, reglas y eliminados.
def texto_whatsapp(partido=None):
    c = cfg()
    if partido is None:
        partido = partido_actual()
    items = anotados(partido["id"]) if partido else []
    nomina = [i for i in items if i["lista"] == "nomina"]
    espera = [i for i in items if i["lista"] == "espera"]
    multas = multas_lista()
    pendientes = [m for m in multas if m["estado"] == "pendiente"]
    expulsados = {j["id"] for j in jugadores_lista() if j["expulsado"]}
    total = cupo_por_genero(c, "F") + cupo_por_genero(c, "M")
    L = [c["nombre_grupo"], "*SOLO DIRECTIVA MANIPULA LA NÓMINA*", "Decir voy + nombre + apellido"]
    if not partido:
        L += ["", "No hay partido en uso."]
        L += ["", "*LISTADO DE MULTAS:*"]
        for m in pendientes:
            if m["participante_id"] in expulsados:
                continue
            abono = f" *abono*: {m['abono']:,}".replace(",", ".") if m["abono"] else ""
            L.append(f"*{m['nombre']}* Fecha: {m['fecha_es']}"
                     + f" valor: {m['valor']:,}".replace(",", ".")
                     + abono + f" *Plazo máx*: {m['plazo_es']}")
        L += ["", "*REGLAS DEL GRUPO:*", c["reglas"], "", "*REGLAMENTO DE MULTAS*",
              c["reglamento_multas"], "", "*ELIMINADOS POR NO PAGAR MULTAS*"]
        actual, n = None, 0
        for m in sorted((m for m in pendientes if m["participante_id"] in expulsados),
                        key=lambda m: (m["nombre"], m["fecha"])):
            if m["nombre"] != actual:
                actual, n = m["nombre"], 0
                L.append(f"*{actual}*")
            n += 1
            abono = f" *abono*: {m['abono']:,}".replace(",", ".") if m["abono"] else ""
            L.append(f"{n}. Fecha: {m['fecha_es']}" + f" valor: {m['valor']:,}".replace(",", ".")
                     + abono + f" *Plazo máx pagar*: {m['plazo_es']}")
        return "\n".join(L)
    L += ["", "*Lugar*: " + partido["cancha"], "*Día*: *" + (dia_semana(partido["fecha"]) or c["dia"]) + "*",
         "*Hora*: " + hora_es(partido["hora"]), "*Fecha*: " + fecha_es(partido["fecha"]), ""]
    # Numeración por bloques de género: las mujeres ocupan los puestos 1..cupos_f
    # y los hombres los siguientes, sin importar el orden en que se anotaron.
    # Así, con 6 cupos de mujer y 6 de hombre, la primera mujer es el puesto 1 y
    # el primer hombre el puesto 7 (se espera completar los cupos de mujer).
    cupos_f = cupo_por_genero(c, "F")
    puestos = {}
    p = 1
    for i in nomina:
        if i["genero"] == "F":
            puestos[p] = i
            p += 1
    p = max(cupos_f + 1, p)  # el bloque de hombres empieza justo después del de mujeres
    for i in nomina:
        if i["genero"] != "F":
            if p > total:
                break
            puestos[p] = i
            p += 1
    for n in range(1, total + 1):
        i = puestos.get(n)
        if i:
            emoji = c["emoji_f"] if i["genero"] == "F" else c["emoji_m"]
            extra = f" ({i['invitado_por']})" if i["invitado_por"] else ""
            L.append(f"{n}:{emoji} {i['nombre']}{extra}")
        else:
            L.append(f"{n}:")
    L += ["", "*LISTA DE ESPERA:*"]
    for n, i in enumerate(espera, 1):
        extra = f" ({i['invitado_por']})" if i["invitado_por"] else ""
        L.append(f"{n}. {i['nombre']}{extra}")
    L += ["", "*LISTADO DE MULTAS:*"]
    for m in pendientes:
        if m["participante_id"] in expulsados:
            continue
        abono = f" *abono*: {m['abono']:,}".replace(",", ".") if m["abono"] else ""
        L.append(f"*{m['nombre']}* Fecha: {m['fecha_es']}"
                 + f" valor: {m['valor']:,}".replace(",", ".")
                 + abono + f" *Plazo máx*: {m['plazo_es']}")
    L += ["", "*REGLAS DEL GRUPO:*", c["reglas"], "", "*REGLAMENTO DE MULTAS*",
          c["reglamento_multas"], "", "*ELIMINADOS POR NO PAGAR MULTAS*"]
    actual, n = None, 0
    for m in sorted((m for m in pendientes if m["participante_id"] in expulsados),
                    key=lambda m: (m["nombre"], m["fecha"])):
        if m["nombre"] != actual:
            actual, n = m["nombre"], 0
            L.append(f"*{actual}*")
        n += 1
        abono = f" *abono*: {m['abono']:,}".replace(",", ".") if m["abono"] else ""
        L.append(f"{n}. Fecha: {m['fecha_es']}" + f" valor: {m['valor']:,}".replace(",", ".")
                 + abono + f" *Plazo máx pagar*: {m['plazo_es']}")
    return "\n".join(L)


# ---------------------------------------------------------------- operaciones
# Aquí está la lógica de negocio: cada función recibe lo que envió el navegador
# y hace su trabajo sobre la base de datos.

# resolver_participante(datos, crear_si_falta) -> busca a un jugador por su id
# o por su nombre. Si no existe y "crear_si_falta" es True, lo crea (según el
# género enviado). Si es False, devuelve un error pidiendo que lo agregue antes.
def resolver_participante(datos, crear_si_falta=True):
    pid = datos.get("participante_id")
    if pid:
        fila = DB.execute("SELECT * FROM participantes WHERE id = ?", (pid,)).fetchone()
        if not fila:
            raise ErrorApp("Ese jugador no existe")
        return dict(fila)
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ErrorApp("Escribe el nombre")
    for fila in DB.execute("SELECT * FROM participantes"):
        if normalizar(fila["nombre"]) == normalizar(nombre):
            return dict(fila)
    if not crear_si_falta:
        raise ErrorApp("Ese jugador no está en la base. Agrégalo primero desde el módulo Jugadores.")
    invitar = not bool(datos.get("miembro"))
    if invitar and not datos.get("permite_crear_invitado"):
        raise ErrorApp("Los invitados deben agregarse primero desde el módulo de participantes")
    genero = (datos.get("genero") or "").upper()
    if genero not in ("F", "M"):
        raise ErrorApp("Ese nombre no está en la base: indica el género (F/M) para crearlo")
    cur = DB.execute(
        "INSERT INTO participantes (nombre, genero, miembro) VALUES (?,?,?)",
        (nombre, genero, 1 if datos.get("miembro") else 0),
    )
    DB.commit()
    return dict(DB.execute("SELECT * FROM participantes WHERE id = ?",
                           (cur.lastrowid,)).fetchone())


# anotar(datos) -> registra a una persona en un partido (nómina o espera).
# Decide automáticamente si entra a la nómina o a espera según:
#   - cupos por género disponibles
#   - si es invitado (solo entran a la nómina tras el corte de invitados)
#   - si fue expulsado o inactivado por multas (se rechaza con "forzar")
# Los invitados sin ficha se guardan directo con su nombre y género.
def anotar(datos):
    c = cfg()
    pid_vista = entero(datos.get("partido_id"), 0) or None
    partido = partido_actual()
    if pid_vista:
        fila = DB.execute("SELECT * FROM partidos WHERE id = ? AND estado != 'cancelada'",
                          (pid_vista,)).fetchone()
        if not fila:
            raise ErrorApp("Ese partido no existe")
        partido = dict(fila)
    if not partido:
        raise ErrorApp("No hay partido en uso. Crea uno o usa un partido guardado desde la pestaña Partidos.")
    es_invitado = not bool(datos.get("miembro"))
    pid = datos.get("participante_id")
    nombre = (datos.get("nombre") or "").strip()
    p = None
    if pid:
        fila = DB.execute("SELECT * FROM participantes WHERE id = ?", (pid,)).fetchone()
        if not fila:
            raise ErrorApp("Ese jugador no existe")
        p = dict(fila)
    elif nombre:
        for fila in DB.execute("SELECT * FROM participantes"):
            if normalizar(fila["nombre"]) == normalizar(nombre):
                p = dict(fila)
                break

    if p is None:
        # Invitado sin ficha: se registra directo en la nómina, sin crear jugador.
        if not nombre:
            raise ErrorApp("Escribe el nombre")
        if not es_invitado:
            raise ErrorApp("Ese jugador no está en la base. Agrégalo primero desde el módulo Jugadores.")
        genero = (datos.get("genero") or "").upper()
        if genero not in ("F", "M"):
            raise ErrorApp("Indica el género (F/M) del invitad@")
        registrados = DB.execute(
            "SELECT nombre_libre FROM nomina WHERE partido_id = ? AND participante_id IS NULL",
            (partido["id"],),
        ).fetchall()
        if any(normalizar(r["nombre_libre"]) == normalizar(nombre) for r in registrados):
            raise ErrorApp(f"{nombre} ya está registrad@")
        lista = datos.get("lista")
        if lista not in ("nomina", "espera"):
            lista = "nomina" if puede_entrar_nomina(partido["id"], genero, c) else "espera"
        if lista == "nomina" and not puede_entrar_nomina(partido["id"], genero, c) \
                and not datos.get("forzar"):
            lista = "espera"
        if lista == "nomina" and not permite_invitados(partido) and not datos.get("forzar"):
            lista = "espera"
        ahora = datetime.now().isoformat(timespec="seconds")
        DB.execute(
            "INSERT INTO nomina (partido_id, participante_id, lista, invitado_por,"
            " nombre_libre, genero_libre, creado) VALUES (?,?,?,?,?,?,?)",
            (partido["id"], None, lista, (datos.get("invitado_por") or "").strip(),
             nombre, genero, ahora),
        )
        DB.commit()
        return {"ok": True, "lista": lista, "nombre": nombre}

    if DB.execute("SELECT 1 FROM nomina WHERE partido_id = ? AND participante_id = ?",
                  (partido["id"], p["id"])).fetchone():
        raise ErrorApp(f"{p['nombre']} ya está registrada")
    if p["expulsado"] and not datos.get("forzar"):
        raise ErrorApp(f"{p['nombre']} está expulsad@ por multas sin pagar")
    if not p["activo"] and not datos.get("forzar"):
        raise ErrorApp(f"{p['nombre']} está inactiv@")
    items = anotados(partido["id"])
    nomina = [i for i in items if i["lista"] == "nomina"]
    lista = datos.get("lista")
    if lista not in ("nomina", "espera"):
        usados = sum(1 for i in nomina if i["genero"] == p["genero"])
        limite = cupo_por_genero(c, p["genero"])
        if len(nomina) >= (entero(c["cupos_mujeres"], 6) + entero(c["cupos_hombres"], 6)):
            lista = "espera"
        elif usados < limite:
            lista = "nomina"
        else:
            lista = "espera"
    if lista == "nomina":
        if not p["miembro"] and not permite_invitados(partido) and not datos.get("forzar"):
            lista = "espera"
        elif not puede_entrar_nomina(partido["id"], p["genero"], c):
            if not datos.get("forzar"):
                lista = "espera"
            else:
                pass
    ahora = datetime.now().isoformat(timespec="seconds")
    DB.execute(
        "INSERT INTO nomina (partido_id, participante_id, lista, invitado_por, creado)"
        " VALUES (?,?,?,?,?)",
        (partido["id"], p["id"], lista, (datos.get("invitado_por") or "").strip(), ahora),
    )
    DB.commit()
    deuda = DB.execute(
        "SELECT COALESCE(SUM(valor - abono), 0) d FROM multas"
        " WHERE participante_id = ? AND estado = 'pendiente'", (p["id"],)
    ).fetchone()["d"]
    aviso = f"Ojo: {p['nombre']} debe ${deuda:,}".replace(",", ".") if deuda else ""
    return {"ok": True, "lista": lista, "nombre": p["nombre"], "aviso": aviso}


# quitar(nid) -> saca a alguien de la nómina/espera. Si salía de la nómina,
# intenta subir a la primera persona de espera del mismo género (regla 3).
def quitar(nid):
    fila = DB.execute(
        "SELECT n.*, p.genero, p.nombre FROM nomina n"
        " LEFT JOIN participantes p ON p.id = n.participante_id WHERE n.id = ?", (nid,)
    ).fetchone()
    if not fila:
        raise ErrorApp("Registro no encontrado", 404)
    DB.execute("DELETE FROM nomina WHERE id = ?", (nid,))
    DB.commit()
    nombre = fila["nombre"] or fila["nombre_libre"]
    genero = fila["genero"] or fila["genero_libre"]
    mensaje = f"{nombre} salió de la lista"
    if fila["lista"] == "nomina":
        sube = ascender(fila["partido_id"], genero)
        if sube:
            mensaje += f". Entra {sube} de la lista de espera (regla 3)"
    return {"ok": True, "mensaje": mensaje}


def ascender(partido_id, genero_libre=None):
    """Promueve de la lista de espera al primer jugador que aún tenga cupo disponible."""
    c = cfg()
    espera = [i for i in anotados(partido_id) if i["lista"] == "espera"]
    if not espera:
        return None
    if genero_libre:
        candidatos = [i for i in espera if i["genero"] == genero_libre]
        if not candidatos:
            candidatos = [i for i in espera if i["genero"] != genero_libre]
    else:
        candidatos = espera
    elegido = None
    for i in candidatos:
        if puede_entrar_nomina(partido_id, i["genero"], c):
            elegido = i
            break
    if not elegido:
        return None
    ahora = datetime.now().isoformat(timespec="seconds")
    DB.execute("UPDATE nomina SET lista = 'nomina', creado = ? WHERE id = ?",
               (ahora, elegido["id"]))
    DB.commit()
    return elegido["nombre"]


# autocompletar(q, limite, partido_id) -> lista de jugadores sugeridos al
# escribir en el cuadro de búsqueda. Marca quién ya está anotado y su deuda.
def autocompletar(q, limite=10, partido_id=None):
    n = normalizar(q)
    partido = None
    if partido_id:
        fila = DB.execute("SELECT * FROM partidos WHERE id = ? AND estado != 'cancelada'",
                          (partido_id,)).fetchone()
        partido = dict(fila) if fila else None
    if partido is None:
        partido = partido_actual()
    registrados = anotados(partido["id"]) if partido else []
    ya = {i["pid"] for i in registrados if i["pid"]}
    ya_libres = {normalizar(i["nombre"]) for i in registrados if not i["pid"]}
    deudas = {
        r["participante_id"]: r["deuda"] for r in DB.execute(
            "SELECT participante_id, SUM(valor - abono) deuda FROM multas"
            " WHERE estado = 'pendiente' GROUP BY participante_id")
    }
    filas = []
    for f in DB.execute("SELECT * FROM participantes ORDER BY nombre COLLATE NOCASE"):
        if not f["activo"]:
            continue
        d = dict(f)
        d["anotado"] = d["id"] in ya or normalizar(d["nombre"]) in ya_libres
        d["deuda"] = max(0, deudas.get(d["id"], 0))
        filas.append(d)
    if not n:
        return filas[:limite]
    empieza = [f for f in filas if normalizar(f["nombre"]).startswith(n)]
    contiene = [f for f in filas if n in normalizar(f["nombre"]) and f not in empieza]
    return (empieza + contiene)[:limite]


# canchas_lista(q, limite) -> canchas guardadas en la base (tabla "canchas"),
# para el autocompletado del formulario de partidos. Devuelve listas de
# diccionarios con "id" y "nombre". Ordena primero las que empiezan con lo
# escrito y luego las que solo lo contienen.
def canchas_lista(q="", limite=50):
    n = normalizar(q)
    filas = [dict(f) for f in DB.execute(
        "SELECT id, nombre FROM canchas ORDER BY nombre COLLATE NOCASE")]
    if n:
        empieza = [f for f in filas if normalizar(f["nombre"]).startswith(n)]
        contiene = [f for f in filas if n in normalizar(f["nombre"]) and f not in empieza]
        filas = empieza + contiene
    return filas[:limite]


def agregar_cancha(nombre):
    """Guarda una cancha nueva en la tabla de canchas (para el formulario de partidos)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorApp("Escribe el nombre de la cancha")
    if DB.execute("SELECT 1 FROM canchas WHERE nombre = ? COLLATE NOCASE",
                  (nombre,)).fetchone():
        raise ErrorApp("Esa cancha ya existe")
    DB.execute("INSERT INTO canchas (nombre) VALUES (?)", (nombre,))
    DB.commit()
    return {"ok": True, "cancha": nombre}


def editar_cancha(ident, nombre):
    """Renombra una cancha guardada (el texto de los partidos ya creados no cambia)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorApp("Escribe el nombre de la cancha")
    if not DB.execute("SELECT 1 FROM canchas WHERE id = ?", (ident,)).fetchone():
        raise ErrorApp("Esa cancha no existe", 404)
    if DB.execute("SELECT 1 FROM canchas WHERE nombre = ? COLLATE NOCASE AND id != ?",
                  (nombre, ident)).fetchone():
        raise ErrorApp("Esa cancha ya existe")
    DB.execute("UPDATE canchas SET nombre = ? WHERE id = ?", (nombre, ident))
    DB.commit()
    return {"ok": True}


def borrar_cancha(ident):
    """Borra una cancha guardada. Los partidos que la usaban quedan con su texto."""
    DB.execute("DELETE FROM canchas WHERE id = ?", (ident,))
    DB.commit()
    return {"ok": True}


# parsear_voy("voy juan chavez (invitado de Cristian)") ->
# devuelve ("juan chavez", "invitado de Cristian"). Extrae el nombre y el
# "invitado de..." de un mensaje que alguien escribe igual en WhatsApp.
def parsear_voy(texto):
    """'voy juan chavez (invitado de Cristian)' -> ('juan chavez', 'invitado de Cristian')."""
    t = re.sub(r"^\s*(yo\s+)?voy\s*(\+|:|,)?\s*", "", (texto or "").strip(), flags=re.IGNORECASE)
    invitado_por = ""
    m = re.search(r"\(([^)]*)\)", t)
    if m:
        invitado_por = m.group(1).strip()
        t = t[:m.start()].strip()
    return t.strip(), invitado_por


# ------------------------------------------------------------------- servidor
# El servidor recibe las peticiones del navegador y las responde. Cada petición
# (GET/POST/DELETE) se enruta a la función que corresponde.

# Handler -> la clase que atiende cada visita del navegador.
class Handler(BaseHTTPRequestHandler):
    server_version = "Nomina/2.0"

    def log_message(self, fmt, *args):
        pass

    # token(): lee la cookie "nomina_token" que el navegador envía con cada
    # petición. Es la llave que identifica la sesión (o None si no hay).
    def token(self):
        m = re.search(r"nomina_token=([A-Za-z0-9_-]+)", self.headers.get("Cookie") or "")
        return m.group(1) if m else None

    # rol(): dice si quien visita es "directiva" o "invitado".
    # Si la config no tiene PIN, todo el mundo es directiva.
    def rol(self):
        if not cfg()["pin"].strip():
            return "directiva"
        sesion = session_get(self.token())
        return sesion["rol"] if sesion else "invitado"

    # exigir_directiva(): si el visitante no es directiva, lanza error 403,
    # de modo que no pueda modificar la nómina ni las multas.
    def exigir_directiva(self):
        if self.rol() != "directiva":
            raise ErrorApp("Solo la DIRECTIVA puede modificar la nómina", 403)

    # cuerpo_json(): lee el cuerpo de la petición (los datos JSON que envió
    # el navegador) y lo devuelve como diccionario de Python.
    def cuerpo_json(self):
        largo = entero(self.headers.get("Content-Length"), 0)
        if not largo:
            return {}
        try:
            return json.loads(self.rfile.read(largo).decode("utf-8"))
        except json.JSONDecodeError:
            raise ErrorApp("Datos inválidos")

    # responder(datos, codigo, cookie) -> manda la respuesta al navegador
    # en formato JSON. "datos" es un diccionario que Python convierte a JSON.
    def responder(self, datos, codigo=200, cookie=None):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(cuerpo)

        # archivo(ruta) -> sirve un archivo estático (HTML, CSS, JS, imágenes)
    # desde la carpeta "static". "/" equivale a /index.html.
    def archivo(self, ruta):
        ruta = "/index.html" if ruta in ("/", "") else ruta
        destino = os.path.normpath(os.path.join(STATIC_DIR, ruta.lstrip("/")))
        if not destino.startswith(STATIC_DIR) or not os.path.isfile(destino):
            self.send_error(404)
            return
        tipos = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".webmanifest": "application/manifest+json",
                 ".svg": "image/svg+xml", ".png": "image/png"}
        with open(destino, "rb") as fh:
            cuerpo = fh.read()
        self.send_response(200)
        self.send_header("Content-Type",
                         tipos.get(os.path.splitext(destino)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

        # do_GET() -> atiende las peticiones tipo "obtener datos". Si la ruta no
    # empieza con /api/ es un archivo (HTML/CSS/JS); si es API, responde datos:
    #   /api/estado         -> todo lo que pinta la pantalla
    #   /api/participantes  -> sugerencias para el buscador (q, limite, partido_id)
    #   /api/texto          -> el mensaje de WhatsApp
    def do_GET(self):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            self.archivo(u.path)
            return
        try:
            with conexion_peticion():
                if u.path == "/api/estado":
                    args = parse_qs(u.query)
                    pid = entero((args.get("id") or [""])[0], 0) or None
                    self.responder(estado_completo(self.rol(), pid))
                elif u.path == "/api/participantes":
                    args = parse_qs(u.query)
                    limite = min(500, max(1, entero((args.get("limite") or ["10"])[0], 10)))
                    pid = entero((args.get("partido_id") or [""])[0], 0) or None
                    self.responder({"resultados": autocompletar(
                        (args.get("q") or [""])[0], limite, pid)})
                elif u.path == "/api/texto":
                    self.responder({"texto": texto_whatsapp()})
                elif u.path == "/api/canchas":
                    args = parse_qs(u.query)
                    limite = min(20, max(1, entero((args.get("limite") or ["10"])[0], 10)))
                    self.responder({"resultados": canchas_lista(
                        (args.get("q") or [""])[0], limite)})
                else:
                    self.responder({"error": "Ruta no encontrada"}, 404)
        except ErrorApp as e:
            self.responder({"error": e.mensaje}, e.codigo)

        # do_POST() / do_DELETE() -> atienden peticiones que cambian datos.
    # Leen el JSON enviado y lo pasan a enrutar(). Las escrituras van con
    # conexión propia Y candado (_escribir_lock) para no pisarse entre usuarios.
    def do_POST(self):
        try:
            datos = self.cuerpo_json()
            with conexion_peticion(escribir=True):
                self.enrutar(urlparse(self.path).path, datos)
        except ErrorApp as e:
            self.responder({"error": e.mensaje}, e.codigo)

    do_DELETE = do_POST

    # -------------------------------------------------------------- rutas API
    # enrutar(ruta, datos) -> el "mapa" de la API: decide qué función llamar
    # según la ruta. Primero maneja el login/logout (sin exigir sesión) y luego
    # obliga a que la directiva esté logueada para todo lo demás.
    def enrutar(self, ruta, datos):
        if ruta == "/api/login":
            pin = cfg()["pin"].strip()
            if not pin or (datos.get("pin") or "").strip() != pin:
                raise ErrorApp("PIN incorrecto", 401)
            token = secrets.token_urlsafe(24)
            session_set(token, {"rol": "directiva", "nombre": datos.get("nombre") or "directiva"})
            self.responder({"ok": True, "rol": "directiva"},
                           cookie=f"nomina_token={token}; Path=/; HttpOnly; SameSite=Lax")
            return
        if ruta == "/api/logout":
            session_del(self.token())
            self.responder({"ok": True}, cookie="nomina_token=; Path=/; Max-Age=0")
            return

        self.exigir_directiva()
        m = re.fullmatch(r"/api/(nomina|multas|jugadores|partidos|motivos|canchas)/(\d+)(?:/(\w+))?", ruta)
        if m:
            self.enrutar_item(m.group(1), int(m.group(2)), m.group(3), datos)
        elif ruta == "/api/nomina":
            if datos.get("texto"):
                nombre, invitado = parsear_voy(datos["texto"])
                datos = dict(datos, nombre=datos.get("nombre") or nombre,
                             invitado_por=datos.get("invitado_por") or invitado)
            self.responder(anotar(datos))
        elif ruta == "/api/jugadores":
            p = resolver_participante({**dict(datos, participante_id=None), "permite_crear_invitado": True})
            self.responder({"ok": True, "jugador": p})
        elif ruta == "/api/multas":
            self.responder(registrar_multa(datos))
        elif ruta == "/api/partidos":
            c = cfg()
            fecha = (datos.get("fecha") or "").strip()
            cancha = (datos.get("cancha") or "").strip()
            hora = (datos.get("hora") or "").strip()
            if not fecha:
                raise ErrorApp("Selecciona la fecha del partido")
            if not cancha:
                raise ErrorApp("Escribe la cancha del partido")
            if not hora:
                raise ErrorApp("Selecciona la hora del partido")
            pid = crear_partido(fecha, hora, cancha)
            # Solo se pone "en uso" automáticamente si no hay otro partido con
            # fecha anterior: el más antiguo es el próximo a jugarse.
            mas_antiguo = DB.execute(
                "SELECT id FROM partidos WHERE estado != 'cancelada'"
                " ORDER BY fecha ASC, id ASC LIMIT 1"
            ).fetchone()
            if mas_antiguo and mas_antiguo["id"] == pid:
                DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
                DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (pid,))
                DB.commit()
            self.responder({"ok": True, "id": pid, "en_uso": bool(
                mas_antiguo and mas_antiguo["id"] == pid)})
        elif ruta == "/api/motivos":
            texto = (datos.get("texto") or "").strip()
            valor = entero(datos.get("valor"), 0)
            if not texto:
                raise ErrorApp("Escribe el motivo de la multa")
            if valor <= 0:
                raise ErrorApp("El valor del motivo debe ser mayor a 0")
            if DB.execute("SELECT 1 FROM motivos_multa WHERE texto = ? COLLATE NOCASE",
                          (texto,)).fetchone():
                raise ErrorApp("Ese motivo ya existe")
            DB.execute("INSERT INTO motivos_multa (texto, valor) VALUES (?,?)", (texto, valor))
            DB.commit()
            self.responder({"ok": True})
        elif ruta == "/api/canchas":
            self.responder(agregar_cancha(datos.get("nombre") or ""))
        elif ruta == "/api/config":
            for k, v in (datos or {}).items():
                if k in CONFIG_DEFAULT or k == "pin":
                    DB.execute("UPDATE config SET valor = ? WHERE clave = ?", (str(v), k))
            DB.commit()
            self.responder({"ok": True})
        else:
            self.responder({"error": "Ruta no encontrada"}, 404)

    # enrutar_item(recurso, ident, accion, datos) -> atiende las peticiones sobre
# un elemento concreto: /api/nomina/3, /api/multas/2/pagar, /api/jugadores/5, etc.
# Dependiendo de "recurso" y "accion" hace la operación (borrar, mover, pagar,
# abonar, editar, usar...) y siempre termina respondiendo {"ok": True}.
def enrutar_item(self, recurso, ident, accion, datos):
        if recurso == "nomina":
            if self.command == "DELETE":
                self.responder(quitar(ident))
            elif accion == "mover":
                if datos.get("lista") not in ("nomina", "espera"):
                    raise ErrorApp("Lista inválida")
                fila = DB.execute(
                    "SELECT n.partido_id, n.lista, p.genero, n.genero_libre, p.miembro"
                    " FROM nomina n"
                    " LEFT JOIN participantes p ON p.id = n.participante_id WHERE n.id = ?",
                    (ident,),
                ).fetchone()
                if not fila:
                    raise ErrorApp("Registro no encontrado", 404)
                c = cfg()
                genero = fila["genero"] or fila["genero_libre"]
                if datos["lista"] == "nomina":
                    if not puede_entrar_nomina(fila["partido_id"], genero, c):
                        raise ErrorApp("No hay cupo disponible para ese género")
                    if not fila["miembro"]:
                        partido = DB.execute(
                            "SELECT * FROM partidos WHERE id = ?", (fila["partido_id"],)
                        ).fetchone()
                        if partido and not permite_invitados(dict(partido)):
                            raise ErrorApp(
                                "El corte de invitados aún no pasa: solo entran a la nómina "
                                "después de las 9am del día del partido")
                ahora = datetime.now().isoformat(timespec="seconds")
                DB.execute("UPDATE nomina SET lista = ?, creado = ? WHERE id = ?",
                           (datos["lista"], ahora, ident))
                DB.commit()
                self.responder({"ok": True})
            else:
                raise ErrorApp("Acción inválida")
        elif recurso == "multas":
            if self.command == "DELETE":
                DB.execute("DELETE FROM multas WHERE id = ?", (ident,))
            elif accion == "pagar":
                DB.execute("UPDATE multas SET estado = 'pagada', abono = valor WHERE id = ?",
                           (ident,))
            elif accion == "abonar":
                abono = entero(datos.get("abono"), 0)
                if abono <= 0:
                    raise ErrorApp("El abono debe ser mayor a 0")
                DB.execute("UPDATE multas SET abono = MIN(valor, abono + ?) WHERE id = ?",
                           (abono, ident))
                DB.execute("UPDATE multas SET estado = 'pagada'"
                           " WHERE id = ? AND abono >= valor", (ident,))
            elif accion == "editar":
                campos = {"fecha": str, "valor": int, "abono": int, "motivo": str,
                          "plazo": str, "participante_id": int}
                if not any(k in datos for k in campos):
                    raise ErrorApp("Sin datos para editar")
                if "participante_id" in datos:
                    pid = entero(datos["participante_id"], 0)
                    existe = DB.execute("SELECT id FROM participantes WHERE id = ?", (pid,)).fetchone()
                    if not existe:
                        raise ErrorApp("El jugador seleccionado no existe")
                    datos["participante_id"] = pid
                if "valor" in datos:
                    valor = entero(datos["valor"], 0)
                    if valor <= 0:
                        raise ErrorApp("El valor de la multa debe ser mayor a 0")
                    datos["valor"] = valor
                if "abono" in datos:
                    datos["abono"] = max(0, entero(datos["abono"], 0))
                for k, tipo in campos.items():
                    if k in datos:
                        valor = datos[k]
                        DB.execute(f"UPDATE multas SET {k} = ? WHERE id = ?", (valor, ident))
                DB.execute("UPDATE multas SET estado = 'pagada'"
                           " WHERE id = ? AND abono >= valor", (ident,))
            else:
                raise ErrorApp("Acción inválida")
            DB.commit()
            self.responder({"ok": True})
        elif recurso == "jugadores":
            if self.command == "DELETE":
                DB.execute("DELETE FROM participantes WHERE id = ?", (ident,))
                DB.commit()
                self.responder({"ok": True})
                return
            campos = {"nombre": str, "genero": str, "miembro": int, "activo": int,
                      "expulsado": int}
            if "expulsado" in datos:
                if datos["expulsado"] in (1, True, "1", "true"):
                    DB.execute("UPDATE participantes SET expulsado = 1, activo = 0 WHERE id = ?",
                               (ident,))
                else:
                    DB.execute("UPDATE participantes SET expulsado = 0, activo = 1 WHERE id = ?",
                               (ident,))
            for k, tipo in campos.items():
                if k in datos and k != "expulsado":
                    valor = datos[k]
                    if tipo is int:
                        valor = 1 if valor in (1, True, "1", "true") else 0
                    elif k == "genero" and valor not in ("F", "M"):
                        raise ErrorApp("Género inválido")
                    elif k == "nombre" and not str(valor).strip():
                        raise ErrorApp("El nombre no puede quedar vacío")
                    DB.execute(f"UPDATE participantes SET {k} = ? WHERE id = ?", (valor, ident))
            DB.commit()
            self.responder({"ok": True})
        elif recurso == "motivos":
            if self.command == "DELETE":
                DB.execute("DELETE FROM motivos_multa WHERE id = ?", (ident,))
            elif accion == "editar":
                texto = (datos.get("texto") or "").strip()
                valor = entero(datos.get("valor"), 0)
                if not texto:
                    raise ErrorApp("El motivo no puede quedar vacío")
                if valor <= 0:
                    raise ErrorApp("El valor del motivo debe ser mayor a 0")
                DB.execute("UPDATE motivos_multa SET texto = ?, valor = ? WHERE id = ?",
                           (texto, valor, ident))
            else:
                raise ErrorApp("Acción inválida")
            DB.commit()
            self.responder({"ok": True})
        elif recurso == "canchas":
            if self.command == "DELETE":
                borrar_cancha(ident)
            elif accion == "editar":
                editar_cancha(ident, datos.get("nombre") or "")
            else:
                raise ErrorApp("Acción inválida")
            self.responder({"ok": True})
        elif recurso == "partidos":
            if self.command == "DELETE":
                era_activo = DB.execute(
                    "SELECT activo FROM partidos WHERE id = ?", (ident,)
                ).fetchone()
                DB.execute("DELETE FROM partidos WHERE id = ?", (ident,))
                if era_activo and era_activo["activo"]:
                    resto = DB.execute(
                        "SELECT id FROM partidos WHERE estado != 'cancelada'"
                        " ORDER BY fecha DESC, id DESC LIMIT 1"
                    ).fetchone()
                    if resto:
                        DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
                        DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (resto["id"],))
            elif accion == "usar":
                DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
                DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (ident,))
            elif accion == "editar":
                for k in ("fecha", "hora", "cancha"):
                    if datos.get(k):
                        DB.execute(f"UPDATE partidos SET {k} = ? WHERE id = ?", (datos[k], ident))
            else:
                raise ErrorApp("Acción inválida")
            DB.commit()
            self.responder({"ok": True})


# registrar_multa(datos) -> guarda una multa nueva. Pide jugador, motivo,
# fecha y valor; el plazo se calcula con la config si no viene indicado.
def registrar_multa(datos):
    c = cfg()
    nombre = (datos.get("nombre") or "").strip()
    if not datos.get("participante_id") and not nombre:
        raise ErrorApp("Selecciona el jugador para registrar la multa")
    motivo = (datos.get("motivo") or "").strip()
    if not motivo:
        raise ErrorApp("Escribe el motivo de la multa")
    fecha = datos.get("fecha") or ""
    if not fecha:
        raise ErrorApp("Selecciona la fecha de la multa")
    p = resolver_participante(datos, crear_si_falta=False)
    valor = entero(datos.get("valor"), 0)
    if valor <= 0:
        raise ErrorApp("El valor de la multa debe ser mayor a 0")
    plazo = datos.get("plazo") or sumar_dias(fecha, entero(c["plazo_dias"], 15))
    DB.execute(
        "INSERT INTO multas (participante_id, fecha, valor, abono, motivo, plazo)"
        " VALUES (?,?,?,?,?,?)",
        (p["id"], fecha, valor, entero(datos.get("abono"), 0), motivo, plazo),
    )
    DB.commit()
    return {"ok": True, "plazo": plazo}


# main() -> punto de entrada de la app. Prepara la base, arranca el servidor
# y lo deja escuchando en http://localhost:8000 hasta que se corte con Ctrl+C.
def main():
    init_db()
    servidor = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    pin = cfg()["pin"].strip()
    print(f"Nómina lista en http://localhost:{PORT}"
          + (f"  (PIN directiva: {pin})" if pin else "  (sin PIN: todos pueden editar)"))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego")


if __name__ == "__main__":
    main()
