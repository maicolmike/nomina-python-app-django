# Nómina · FAMILIA MIXTO SIN LÍMITES 2023 ❤️

App para administrar la nómina semanal del grupo: cupos por género, lista de espera,
multas, jugadores y el texto listo para pegar en WhatsApp. Solo la **directiva** modifica;
el resto del grupo solo ve.

## Cómo ejecutarla

Necesitas Python 3 (ya viene en Mac y Linux; en Windows se instala desde python.org).

```bash
cd nomina-app
python3 app.py
```

Abre <http://localhost:8000>. Para que otros del grupo entren desde el mismo WiFi,
usa la IP de tu computador, por ejemplo `http://192.168.1.20:8000`.

- PIN inicial de la directiva: **2023** (botón «Directiva» arriba a la derecha).
- Cambiarlo: pestaña **Config** o `NOMINA_PIN=1234 python3 app.py`.
- Otro puerto: `NOMINA_PORT=9000 python3 app.py`.
- Otra ubicación de la base: `NOMINA_DB=/ruta/nomina.db python3 app.py`.

## Dónde se guardan los datos

En el archivo **`nomina.db`** (SQLite) dentro de la carpeta de la app; se crea solo la
primera vez. Ese archivo es tu respaldo: cópialo y tienes todo (participantes, nóminas,
multas, partidos y configuración). Si lo borras, la app arranca de nuevo con los datos
de ejemplo cargados.

## Pestañas

| Pestaña | Qué hace |
| --- | --- |
| **Nómina** | Datos del partido, cupos 🌹/⚽, nómina, lista de espera, anotar con autocompletado («voy + nombre») y texto para WhatsApp. |
| **Partidos** | Crear partidos nuevos, ver el historial y cambiar el estado (abierta, cerrada, en juego, finalizada, cancelada). |
| **Multas** | Deuda total, multas vencidas, registrar multa (con motivos y valores del reglamento), abonar, pagar o borrar. |
| **Jugadores** | Base de participantes: agregar, editar nombre, activar/inactivar, expulsar por multas y borrar. |
| **Config** | Nombre del grupo, cancha, día, hora, hora de corte, cupos, valores de multa, plazo, PIN y los dos reglamentos. |

## Reglas que aplica sola

1. **Antes del corte** (9:00 am por defecto) solo se anotan miembros del grupo y se
   respetan los 6 cupos de mujeres y 6 de hombres; si están llenos, la persona pasa a
   lista de espera.
2. **Después del corte** se puede anotar gente de fuera y, si hace falta, sin respetar
   los cupos por género, siempre que no haya lista de espera.
3. Al **quitar a alguien de la nómina** sube automáticamente la primera persona del mismo
   género que esté en espera; si no hay, sube la primera de la lista.
4. Las **multas** calculan solo su plazo máximo (15 días por defecto) y se marcan
   *vencidas* cuando se pasa la fecha; admiten abonos parciales.
5. Los jugadores marcados como **expulsados** aparecen en el bloque
   «ELIMINADOS POR NO PAGAR MULTAS» del texto de WhatsApp.

La directiva puede saltarse una regla cuando el sistema lo advierte: la app pregunta
antes de anotar igual.

## Permisos

- **Sin PIN:** solo lectura (nómina, espera, multas, jugadores y reglamento).
- **Con PIN:** todos los botones de crear, editar y borrar.
- Para dejar la app sin bloqueo, escribe `SIN-PIN` en el campo de PIN de la pestaña Config.

## Estructura

```
nomina-app/
├── app.py            # servidor + API + base de datos (solo Python estándar)
├── README.md
└── static/
    ├── index.html    # pestañas
    ├── app.js        # lógica de la interfaz
    └── styles.css    # estilo
```
