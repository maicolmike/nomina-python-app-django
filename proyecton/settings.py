# =============================================================================
# settings.py  ->  Configuración del proyecto Django.
#
# Nota: este proyecto NO usa las aplicaciones estándar de Django (admin, auth,
# migrations...). Toda la lógica real vive en app.py y estas vistas solo sirven
# el HTML y responden la API JSON. Por eso el settings es mínimo.
# =============================================================================

from pathlib import Path

# Carpeta raíz del proyecto (donde está manage.py, app.py, static/...)
BASE_DIR = Path(__file__).resolve().parent.parent

# Clave secreta de Django (no crítica aquí, pero la exige el framework).
SECRET_KEY = 'django-insecure-54+p791$byd4gbhwx3#*z^##v=8vh^#@z&g0nnh*faq8upq#l+'

# Producción: False para no mostrar errores sensibles.
DEBUG = False

# En PythonAnywhere tu página queda como TUUSUARIO.pythonanywhere.com.
# Con ['*'] se acepta cualquier dominio (más simple de configurar).
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = []  # no usamos las apps propias de Django

MIDDLEWARE = ['proyecton.middleware.ConexionMiddleware']  # una conexión de base por petición

ROOT_URLCONF = 'proyecton.urls'

TEMPLATES = []  # la interfaz es HTML suelto en static/, no plantillas Django

WSGI_APPLICATION = 'proyecton.wsgi.application'

# Usamos la base SQLite de app.py (nomina.db). Django no la toca.
DATABASES = {}

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = False

# Carpeta con el HTML/CSS/JS de la interfaz.
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']