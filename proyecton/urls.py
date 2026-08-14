# =============================================================================
# urls.py  ->  Mapa de direcciones de la página. Conecta cada ruta del
# navegador (/api/estado, /api/nomina, /style.css...) con su vista en views.py.
# =============================================================================

from django.urls import re_path

from . import views

# Misma estructura de rutas que tenía la app original:
#   /api/...  -> la API (JSON) que entiende static/app.js
#   cualquier otra ruta -> archivos de la interfaz (static/)
urlpatterns = [
    # API GET: estado, buscador de participantes, texto de WhatsApp
    re_path(r"^api/(estado|participantes|texto)$", views.api_get),
    # API login/logout de la directiva
    re_path(r"^api/(login|logout)$", views.api_auth),
    # API de colecciones (crear nómina, jugadores, multas, partidos, motivos, config)
    re_path(r"^api/(nomina|jugadores|multas|partidos|motivos|config)$", views.api_post),
    # API sobre un elemento concreto: /api/nomina/3, /api/multas/2/pagar...
    re_path(r"^api/(nomina|multas|jugadores|partidos|motivos)/(\d+)(?:/(\w+))?$",
            views.api_item),
    # Interfaz: cualquier otra ruta sirve un archivo estático (index.html, css, js)
    re_path(r"^(?P<ruta>.*)$", views.archivo),
]