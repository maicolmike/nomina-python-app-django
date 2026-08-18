# =============================================================================
# views.py  ->  Convierte la antigua app (servidor HTTP propio) a Django.
#
# Reutiliza TODA la lógica de negocio que ya vivía en "app.py" (nómina, multas,
# jugadores, partidos, configuración, etc.). Solo cambia la "capa de entrada":
# antes el navegador hablaba con el Handler de Python puro; ahora estas vistas
# Django reciben esas mismas peticiones y les responden igual (misma API JSON).
#
# Reglas importantes:
#   - Las peticiones POST/DELETE traen JSON sin token CSRF (son de un celular
#     o de la interfaz). Por eso cada vista está decorada con @csrf_exempt.
#   - El acceso de "directiva" se sigue validando con la cookie nomina_token
#     y la tabla de sesiones de app.py (guardada en la base de datos).
# =============================================================================

import json
import re

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

import app as servidor  # la lógica de negocio original (app.py)

# Prepara la base de datos al arrancar (crea tablas, cargas iniciales, etc.)
servidor.init_db()


# ------------------------------------------------------------- utilidades


def _token(request):
    """Le |la cookie nomina_token que identifica la sesión (o None)."""
    m = re.search(r"nomina_token=([A-Za-z0-9_-]+)", request.headers.get("Cookie") or "")
    return m.group(1) if m else None


def _rol(request):
    """Dice si el visitante es 'directiva' o 'invitado' (igual que app.py)."""
    if not servidor.cfg()["pin"].strip():
        return "directiva"
    sesion = servidor.session_get(_token(request))
    return sesion["rol"] if sesion else "invitado"


def _exigir_directiva(request):
    """Si no es directiva, lanza el mismo error 403 de la app original."""
    if _rol(request) != "directiva":
        raise servidor.ErrorApp("Solo la DIRECTIVA puede modificar la nómina", 403)


def _cuerpo(request):
    """Lee el JSON que envió el navegador (o {} si no trae cuerpo)."""
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise servidor.ErrorApp("Datos inválidos")


def _responder(datos, codigo=200, cookie=None):
    """Manda la respuesta JSON."""
    response = JsonResponse(datos, status=codigo, safe=False)
    if cookie:
        response["Set-Cookie"] = cookie
    return response


def _manejar_errors(func):
    """Decorador: si una vista lanza ErrorApp, la convierte en respuesta JSON."""
    def envoltura(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except servidor.ErrorApp as e:
            return _responder({"error": e.mensaje}, e.codigo)
        except Exception:
            import traceback
            traceback.print_exc()
            return _responder({"error": "Error interno del servidor"}, 500)
    return envoltura


# -------------------------------------------------------------------- GETs


@csrf_exempt
@_manejar_errors
def api_get(request, recurso):
    """Rutas GET: estado, participantes (buscador), texto WhatsApp."""
    if recurso == "estado":
        pid = servidor.entero(request.GET.get("id") or "", 0) or None
        return _responder(servidor.estado_completo(_rol(request), pid))
    if recurso == "participantes":
        limite = min(500, max(1, servidor.entero(request.GET.get("limite") or "10", 10)))
        pid = servidor.entero(request.GET.get("partido_id") or "", 0) or None
        return _responder({"resultados": servidor.autocompletar(
            request.GET.get("q") or "", limite, pid)})
    if recurso == "texto":
        return _responder({"texto": servidor.texto_whatsapp()})
    return _responder({"error": "Ruta no encontrada"}, 404)


# ---------------------------------------------------------------- login/logout


@csrf_exempt
@_manejar_errors
def api_auth(request, accion):
    """Login (pedir PIN) y logout de la directiva."""
    if accion == "login":
        datos = _cuerpo(request)
        pin = servidor.cfg()["pin"].strip()
        if not pin or (datos.get("pin") or "").strip() != pin:
            raise servidor.ErrorApp("PIN incorrecto", 401)
        from secrets import token_urlsafe
        token = token_urlsafe(24)
        servidor.session_set(token, {"rol": "directiva", "nombre": datos.get("nombre") or "directiva"})
        return _responder({"ok": True, "rol": "directiva"},
                          cookie=f"nomina_token={token}; Path=/; HttpOnly; SameSite=Lax")
    # logout
    servidor.session_del(_token(request))
    return _responder({"ok": True}, cookie="nomina_token=; Path=/; Max-Age=0")


# ------------------------------------------------------------------ rutas POST


@csrf_exempt
@_manejar_errors
def api_post(request, recurso):
    """Rutas de colección: /api/nomina, /api/jugadores, /api/multas,
    /api/partidos, /api/motivos, /api/canchas y /api/config."""
    if recurso == "canchas" and request.method == "GET":
        limite = min(20, max(1, servidor.entero(request.GET.get("limite") or "10", 10)))
        return _responder({"resultados": servidor.canchas_lista(
            request.GET.get("q") or "", limite)})
    _exigir_directiva(request)
    datos = _cuerpo(request)

    if recurso == "nomina":
        if datos.get("texto"):
            nombre, invitado = servidor.parsear_voy(datos["texto"])
            datos = dict(datos, nombre=datos.get("nombre") or nombre,
                         invitado_por=datos.get("invitado_por") or invitado)
        return _responder(servidor.anotar(datos))

    if recurso == "jugadores":
        p = servidor.resolver_participante(
            {**dict(datos, participante_id=None), "permite_crear_invitado": True})
        return _responder({"ok": True, "jugador": p})

    if recurso == "multas":
        return _responder(servidor.registrar_multa(datos))

    if recurso == "partidos":
        c = servidor.cfg()
        fecha = (datos.get("fecha") or "").strip()
        cancha = (datos.get("cancha") or "").strip()
        hora = (datos.get("hora") or "").strip()
        if not fecha:
            raise servidor.ErrorApp("Selecciona la fecha del partido")
        if not cancha:
            raise servidor.ErrorApp("Escribe la cancha del partido")
        if not hora:
            raise servidor.ErrorApp("Selecciona la hora del partido")
        pid = servidor.crear_partido(fecha, hora, cancha)
        mas_antiguo = servidor.DB.execute(
            "SELECT id FROM partidos WHERE estado != 'cancelada'"
            " ORDER BY fecha ASC, id ASC LIMIT 1"
        ).fetchone()
        if mas_antiguo and mas_antiguo["id"] == pid:
            servidor.DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
            servidor.DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (pid,))
            servidor.DB.commit()
        return _responder({"ok": True, "id": pid, "en_uso": bool(
            mas_antiguo and mas_antiguo["id"] == pid)})

    if recurso == "motivos":
        texto = (datos.get("texto") or "").strip()
        valor = servidor.entero(datos.get("valor"), 0)
        if not texto:
            raise servidor.ErrorApp("Escribe el motivo de la multa")
        if valor <= 0:
            raise servidor.ErrorApp("El valor del motivo debe ser mayor a 0")
        if servidor.DB.execute("SELECT 1 FROM motivos_multa WHERE texto = ? COLLATE NOCASE",
                               (texto,)).fetchone():
            raise servidor.ErrorApp("Ese motivo ya existe")
        servidor.DB.execute("INSERT INTO motivos_multa (texto, valor) VALUES (?,?)", (texto, valor))
        servidor.DB.commit()
        return _responder({"ok": True})

    if recurso == "canchas":
        return _responder(servidor.agregar_cancha(datos.get("nombre") or ""))

    if recurso == "config":
        for k, v in (datos or {}).items():
            if k in servidor.CONFIG_DEFAULT or k == "pin":
                servidor.DB.execute("UPDATE config SET valor = ? WHERE clave = ?", (str(v), k))
        servidor.DB.commit()
        return _responder({"ok": True})

    return _responder({"error": "Ruta no encontrada"}, 404)


# ------------------------------------------------------- rutas sobre 1 elemento


@csrf_exempt
@_manejar_errors
def api_item(request, recurso, ident, accion=None):
    """Rutas sobre un elemento concreto: /api/nomina/3, /api/multas/2/pagar...
    Reproduce exactamente la función enrutar_item() de app.py."""
    _exigir_directiva(request)
    datos = _cuerpo(request)
    id_ = int(ident)

    if recurso == "nomina":
        if request.method == "DELETE":
            return _responder(servidor.quitar(id_))
        if accion == "mover":
            if datos.get("lista") not in ("nomina", "espera"):
                raise servidor.ErrorApp("Lista inválida")
            fila = servidor.DB.execute(
                "SELECT n.partido_id, n.lista, p.genero, n.genero_libre, p.miembro"
                " FROM nomina n"
                " LEFT JOIN participantes p ON p.id = n.participante_id WHERE n.id = ?",
                (id_,),
            ).fetchone()
            if not fila:
                raise servidor.ErrorApp("Registro no encontrado", 404)
            c = servidor.cfg()
            genero = fila["genero"] or fila["genero_libre"]
            if datos["lista"] == "nomina":
                if not servidor.puede_entrar_nomina(fila["partido_id"], genero, c):
                    raise servidor.ErrorApp("No hay cupo disponible para ese género")
                if not fila["miembro"]:
                    partido = servidor.DB.execute(
                        "SELECT * FROM partidos WHERE id = ?", (fila["partido_id"],)
                    ).fetchone()
                    if partido and not servidor.permite_invitados(dict(partido)):
                        raise servidor.ErrorApp(
                            "El corte de invitados aún no pasa: solo entran a la nómina "
                            "después de las 9am del día del partido")
            now = servidor.datetime.now().isoformat(timespec="seconds")
            servidor.DB.execute("UPDATE nomina SET lista = ?, creado = ? WHERE id = ?",
                                (datos["lista"], now, id_))
            servidor.DB.commit()
            return _responder({"ok": True})
        raise servidor.ErrorApp("Acción inválida")

    if recurso == "multas":
        if request.method == "DELETE":
            servidor.DB.execute("DELETE FROM multas WHERE id = ?", (id_,))
        elif accion == "pagar":
            servidor.DB.execute("UPDATE multas SET estado = 'pagada', abono = valor WHERE id = ?",
                                (id_,))
        elif accion == "abonar":
            abono = servidor.entero(datos.get("abono"), 0)
            if abono <= 0:
                raise servidor.ErrorApp("El abono debe ser mayor a 0")
            servidor.DB.execute("UPDATE multas SET abono = MIN(valor, abono + ?) WHERE id = ?",
                                (abono, id_))
            servidor.DB.execute("UPDATE multas SET estado = 'pagada'"
                                " WHERE id = ? AND abono >= valor", (id_,))
        elif accion == "editar":
            campos = {"fecha": str, "valor": int, "abono": int, "motivo": str,
                      "plazo": str, "participante_id": int}
            if not any(k in datos for k in campos):
                raise servidor.ErrorApp("Sin datos para editar")
            if "participante_id" in datos:
                pid = servidor.entero(datos["participante_id"], 0)
                existe = servidor.DB.execute(
                    "SELECT id FROM participantes WHERE id = ?", (pid,)).fetchone()
                if not existe:
                    raise servidor.ErrorApp("El jugador seleccionado no existe")
                datos["participante_id"] = pid
            if "valor" in datos:
                valor = servidor.entero(datos["valor"], 0)
                if valor <= 0:
                    raise servidor.ErrorApp("El valor de la multa debe ser mayor a 0")
                datos["valor"] = valor
            if "abono" in datos:
                datos["abono"] = max(0, servidor.entero(datos["abono"], 0))
            for k, tipo in campos.items():
                if k in datos:
                    valor = datos[k]
                    servidor.DB.execute(f"UPDATE multas SET {k} = ? WHERE id = ?", (valor, id_))
            servidor.DB.execute("UPDATE multas SET estado = 'pagada'"
                                " WHERE id = ? AND abono >= valor", (id_,))
        else:
            raise servidor.ErrorApp("Acción inválida")
        servidor.DB.commit()
        return _responder({"ok": True})

    if recurso == "jugadores":
        if request.method == "DELETE":
            servidor.DB.execute("DELETE FROM participantes WHERE id = ?", (id_,))
            servidor.DB.commit()
            return _responder({"ok": True})
        campos = {"nombre": str, "genero": str, "miembro": int, "activo": int,
                  "expulsado": int}
        if "expulsado" in datos:
            if datos["expulsado"] in (1, True, "1", "true"):
                servidor.DB.execute("UPDATE participantes SET expulsado = 1, activo = 0 WHERE id = ?",
                                    (id_,))
            else:
                servidor.DB.execute("UPDATE participantes SET expulsado = 0, activo = 1 WHERE id = ?",
                                    (id_,))
        for k, tipo in campos.items():
            if k in datos and k != "expulsado":
                valor = datos[k]
                if tipo is int:
                    valor = 1 if valor in (1, True, "1", "true") else 0
                elif k == "genero" and valor not in ("F", "M"):
                    raise servidor.ErrorApp("Género inválido")
                elif k == "nombre" and not str(valor).strip():
                    raise servidor.ErrorApp("El nombre no puede quedar vacío")
                servidor.DB.execute(f"UPDATE participantes SET {k} = ? WHERE id = ?", (valor, id_))
        servidor.DB.commit()
        return _responder({"ok": True})

    if recurso == "motivos":
        if request.method == "DELETE":
            servidor.DB.execute("DELETE FROM motivos_multa WHERE id = ?", (id_,))
        elif accion == "editar":
            texto = (datos.get("texto") or "").strip()
            valor = servidor.entero(datos.get("valor"), 0)
            if not texto:
                raise servidor.ErrorApp("El motivo no puede quedar vacío")
            if valor <= 0:
                raise servidor.ErrorApp("El valor del motivo debe ser mayor a 0")
            servidor.DB.execute("UPDATE motivos_multa SET texto = ?, valor = ? WHERE id = ?",
                                (texto, valor, id_))
        else:
            raise servidor.ErrorApp("Acción inválida")
        servidor.DB.commit()
        return _responder({"ok": True})

    if recurso == "partidos":
        if request.method == "DELETE":
            era_activo = servidor.DB.execute(
                "SELECT activo FROM partidos WHERE id = ?", (id_,)).fetchone()
            servidor.DB.execute("DELETE FROM partidos WHERE id = ?", (id_,))
            if era_activo and era_activo["activo"]:
                resto = servidor.DB.execute(
                    "SELECT id FROM partidos WHERE estado != 'cancelada'"
                    " ORDER BY fecha DESC, id DESC LIMIT 1").fetchone()
                if resto:
                    servidor.DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
                    servidor.DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (resto["id"],))
        elif accion == "usar":
            servidor.DB.execute("UPDATE partidos SET activo = 0 WHERE activo = 1")
            servidor.DB.execute("UPDATE partidos SET activo = 1 WHERE id = ?", (id_,))
        elif accion == "editar":
            for k in ("fecha", "hora", "cancha"):
                if datos.get(k):
                    servidor.DB.execute(f"UPDATE partidos SET {k} = ? WHERE id = ?", (datos[k], id_))
        else:
            raise servidor.ErrorApp("Acción inválida")
        servidor.DB.commit()
        return _responder({"ok": True})

    return _responder({"error": "Ruta no encontrada"}, 404)


# --------------------------------------------------------------- archivos estáticos


def _archivo(ruta):
    """Lee un archivo de la carpeta static/ y devuelve su contenido."""
    import os
    ruta = "/index.html" if ruta in ("/", "") else ruta
    destino = os.path.normpath(os.path.join(servidor.STATIC_DIR, ruta.lstrip("/")))
    if not destino.startswith(servidor.STATIC_DIR) or not os.path.isfile(destino):
        return None, None
    tipos = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
             ".css": "text/css; charset=utf-8", ".webmanifest": "application/manifest+json",
             ".svg": "image/svg+xml", ".png": "image/png"}
    with open(destino, "rb") as fh:
        cuerpo = fh.read()
    ct = tipos.get(os.path.splitext(destino)[1], "application/octet-stream")
    return cuerpo, ct


@_manejar_errors
def archivo(request, ruta):
    """Sirve la interfaz: / , /index.html, /styles.css, /app.js..."""
    cuerpo, ct = _archivo(ruta)
    if cuerpo is None:
        return HttpResponse("No encontrado", status=404)
    response = HttpResponse(cuerpo, content_type=ct)
    response["Cache-Control"] = "no-store"
    return response