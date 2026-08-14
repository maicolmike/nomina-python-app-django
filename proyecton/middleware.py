# =============================================================================
# middleware.py  ->  Conexión propia de base de datos por cada petición (Django).
#
# Con esto, aunque Django atienda varias peticiones a la vez (varios hilos o
# procesos), cada una usa una conexión SQLite independiente, modo WAL, y las
# escrituras van en fila con el candado de app.py. Es lo que permite que hasta
# ~5 personas usen la app al mismo tiempo sin "database is locked".
# =============================================================================

import app as servidor


class ConexionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        escribir = request.method in ("POST", "DELETE", "PUT")
        with servidor.conexion_peticion(escribir=escribir):
            return self.get_response(request)