# Doday

Doday ayuda a descubrir qué hacer en Medellín: eventos por fecha, categoría,
precio y cercanía al alojamiento, con mapa, ruta, favoritos, propuestas de la
comunidad y un panel de analítica para el equipo. Interfaz en español e inglés.

Hecho con Django 6 y PostgreSQL (SQLite en desarrollo).

## Correr el proyecto en tu computador

Necesitas Python 3.12 o superior.

1. Clonar el repositorio:
   - `git clone https://github.com/JANATAROTO/Doday-Project.git`
   - `cd Doday-Project`
2. Crear y activar el ambiente virtual:
   - `python -m venv venv`
   - Windows: `venv\Scripts\activate` · Linux/macOS: `source venv/bin/activate`
3. Instalar las dependencias: `pip install -r requirements.txt`
4. Crear el archivo de configuración local (no se sube al repositorio):
   - Windows: `copy .env.example .env` · Linux/macOS: `cp .env.example .env`

   `.env` ya trae `DJANGO_DEBUG=True`, que es lo único obligatorio en local.
   Sin ese archivo el proyecto no arranca: por seguridad `DEBUG` viene apagado
   y exige una `DJANGO_SECRET_KEY`.
5. Crear la base de datos: `python manage.py migrate`
6. Opcional, eventos ficticios para probar: `python manage.py seed_events`
7. Crear tu usuario administrador: `python manage.py createsuperuser`
8. Lanzar el servidor: `python manage.py runserver` y abrir http://127.0.0.1:8000/

En local la base de datos es un archivo SQLite (`db.sqlite3`), así que no hay
que instalar nada más. Sin llaves de Google la app funciona igual: los mapas
muestran un aviso y las direcciones piden las coordenadas a mano.

## Configuración

Todo se configura con variables de entorno: en local van en `.env`; en el
servidor, en el panel del proveedor. `.env.example` las lista todas con su
explicación. Las principales:

| Variable | Para qué sirve |
| --- | --- |
| `DJANGO_DEBUG` | `True` solo en local. En producción no se define. |
| `DJANGO_SECRET_KEY` | Obligatoria en producción. Firma sesiones y enlaces. |
| `DATABASE_URL` | Conexión a PostgreSQL. Sin ella se usa SQLite. |
| `GOOGLE_MAPS_API_KEY` | Llave **de navegador**: dibuja los mapas. |
| `GOOGLE_MAPS_SERVER_KEY` | Llave **de servidor**: busca direcciones y calcula rutas. |
| `DJANGO_ALLOWED_HOSTS` | Dominio(s) del sitio en producción. |
| `DJANGO_HTTPS` | `True` cuando el sitio se sirve por HTTPS. |
| `EMAIL_HOST` y relacionadas | Correo para recuperar contraseña. |
| `SENTRY_DSN` | Opcional: reporte de errores a Sentry. |
| `TICKETMASTER_API_KEY` | Importar eventos reales de Ticketmaster (gratis). |

Para revisar qué está configurado y si funciona:

```
python manage.py check_integrations
```

Dice en palabras simples el estado de la base de datos, las llaves de Google,
el correo y la seguridad. Hace una consulta real de prueba a Google (dirección
y ruta); con `--offline` solo revisa la configuración.

### Las dos llaves de Google Maps

Doday usa Google Maps Platform para todo lo geográfico. Son **dos llaves del
mismo proyecto** de Google Cloud, porque se usan en lugares distintos:

| | Llave de navegador | Llave de servidor |
| --- | --- | --- |
| Variable | `GOOGLE_MAPS_API_KEY` | `GOOGLE_MAPS_SERVER_KEY` |
| Quién la ve | Cualquiera (va en la página) | Nadie (solo el servidor) |
| Restricción de aplicación | Sitios web: tu dominio | Ninguna |
| Restricción de API | Maps JavaScript API | Geocoding API y Routes API |

No sirve usar una sola: la de navegador es pública y por eso se limita a tu
sitio web, y Google rechaza las llaves limitadas por sitio web cuando la
consulta sale de un servidor.

En Google Cloud Console (APIs y servicios):

1. **Biblioteca**: habilitar *Maps JavaScript API*, *Geocoding API* y
   *Routes API*.
2. **Credenciales → Crear credenciales → Clave de API**, dos veces, con las
   restricciones de la tabla. En la de navegador, los sitios web son
   `http://127.0.0.1:8000/*`, `http://localhost:8000/*` y, en producción,
   `https://tu-dominio/*`.
3. **Facturación → Presupuestos y alertas**: crear un presupuesto pequeño con
   alerta por correo, para enterarte si el uso se sale de lo normal.

Cada servicio tiene una cuota gratis mensual (10.000 cargas de mapa, 10.000
búsquedas de dirección y 10.000 rutas, a noviembre de 2026). Doday solo pide
una ruta cuando un usuario con sesión iniciada y alojamiento guardado abre un
evento, y solo busca una dirección cuando alguien guarda su alojamiento.

Si una llave se publica por error (en un chat, una captura o un commit),
bórrala en *Credenciales* y crea otra: borrarla es lo único que la invalida.

Dos reglas de Google que el código ya cumple: sus rutas y direcciones solo se
muestran sobre un mapa de Google, y las coordenadas que devuelve se guardan
máximo 30 días (`python manage.py refresh_geocodes` las renueva; se programa
una vez al día).

## Eventos reales

El catálogo se llena de tres formas, todas con eventos reales:

- **Ticketmaster.** `python manage.py sync_external_events` trae los próximos
  eventos en un radio de 40 km alrededor de la zona de servicio. Necesita
  `TICKETMASTER_API_KEY`: es gratis, se obtiene creando una cuenta en
  [developer.ticketmaster.com](https://developer.ticketmaster.com) (es la
  *Consumer Key* de la app que se crea sola) y permite 5.000 consultas al día.
  Se puede repetir cuantas veces se quiera: actualiza los eventos, no los
  duplica.
- **A mano.** Un administrador crea eventos con el botón *Crear evento*.
- **Propuestas.** Cualquier persona propone un evento en *Proponer un evento*
  y un administrador lo aprueba en *Moderación*.

En producción la importación corre sola todos los días con GitHub Actions
(`.github/workflows/sync-events.yml`). Se enciende agregando dos secretos en
GitHub (*Settings → Secrets and variables → Actions*): `DATABASE_URL` (la
cadena de Neon) y `TICKETMASTER_API_KEY`. Con `GOOGLE_MAPS_SERVER_KEY` como
tercer secreto, el mismo trabajo renueva las coordenadas de Google que están
por cumplir 30 días. También se puede lanzar a mano: *Actions → Importar
eventos → Run workflow*.

`seed_events` carga eventos **ficticios** y solo sirve para desarrollo o demos;
no se usa en producción.

## Despliegue (Render + Neon)

La aplicación corre en [Render](https://render.com) y la base de datos en
[Neon](https://neon.tech) (PostgreSQL). Ambos tienen plan gratuito para
empezar; `render.yaml` describe el servicio para crearlo en un paso.

1. **Base de datos.** En Neon, crear un proyecto (región *AWS US East*, la
   misma de Render) y copiar la cadena de conexión **directa** (la que no dice
   `-pooler`), que empieza por `postgresql://`.
2. **Servicio web.** En Render: *New → Blueprint* y elegir este repositorio.
   Render lee `render.yaml` y pide tres valores: `DATABASE_URL` (la cadena de
   Neon), `GOOGLE_MAPS_API_KEY` y `GOOGLE_MAPS_SERVER_KEY`. La
   `DJANGO_SECRET_KEY` la genera Render.
3. En cada despliegue Render ejecuta `build.sh`: instala dependencias, prepara
   los estilos, aplica las migraciones y crea la tabla de caché. Luego arranca
   la app con Gunicorn. Cada `git push` a `main` despliega de nuevo.
4. **Usuario administrador.** El plan gratuito de Render no tiene consola, así
   que se crea desde tu computador apuntando a la base de Neon:
   - Windows (PowerShell): `$env:DATABASE_URL="postgresql://..."` y luego
     `python manage.py createsuperuser`
   - Cierra esa terminal al terminar, para que los siguientes comandos vuelvan
     a usar tu base local.
5. **Llave de navegador.** Agregar `https://<tu-servicio>.onrender.com/*` a
   los sitios web permitidos de la llave de navegador.
6. Verificar: abrir el sitio, iniciar sesión, guardar un alojamiento y abrir
   un evento (debe verse el mapa y la ruta).

Cuando haya dominio propio: agregarlo en Render (*Settings → Custom Domains*),
definir `DJANGO_ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com` y
`DJANGO_CSRF_TRUSTED_ORIGINS=https://tu-dominio.com,https://www.tu-dominio.com`,
y agregar el dominio a la llave de navegador.

Para tener en cuenta del plan gratuito: Render apaga el servicio tras 15
minutos sin visitas y la siguiente tarda cerca de un minuto en cargar; el plan
de pago más pequeño lo mantiene encendido. Neon suspende la base tras unos
minutos sin uso y la despierta sola en un par de segundos.

Lo que hace que esto funcione en producción, por si se cambia de proveedor:
Gunicorn sirve la app, WhiteNoise sirve los estilos (no hace falta Nginx),
`/healthz` responde al chequeo de salud sin tocar la base de datos, los
registros salen por consola y los contadores del límite de intentos se guardan
en la base para que todos los procesos los compartan.

## Comandos útiles

| Comando | Qué hace |
| --- | --- |
| `python manage.py test` | Corre todas las pruebas. |
| `python manage.py check_integrations` | Revisa base de datos, llaves, correo y seguridad. |
| `python manage.py seed_events` | Carga eventos ficticios (solo para desarrollo o demos). |
| `python manage.py refresh_geocodes` | Renueva coordenadas de Google con casi 30 días. |
| `python manage.py sync_external_events` | Importa eventos reales de Ticketmaster (requiere su llave). |
| `python manage.py generate_demo_interactions --days 30` | Llena la analítica con datos simulados (solo demos). |

## Estructura del proyecto

- **events**: catálogo de eventos (crear, editar, detalle), favoritos,
  compartir, enlace de boletas, propuestas de la comunidad y su moderación.
  Solo los eventos aprobados aparecen en el catálogo, la búsqueda y el mapa.
- **search**: filtros sobre el catálogo: palabra clave, categoría, fechas,
  gratuitos, radio y orden por cercanía. La distancia se calcula dentro de la
  base de datos, así que filtrar y ordenar no depende de cuántos eventos haya.
- **navigation**: alojamiento del usuario (con validación de la zona de
  servicio), búsqueda de direcciones, ruta al evento y mapa de eventos.
- **analytics**: registra de forma anónima vistas, favoritos y clics en
  boletas, y muestra al equipo un panel en `/analytics/`.
- **doday**: configuración, límite de intentos (`ratelimit.py`) y chequeo de
  salud (`health.py`).

## Idiomas

La interfaz está en inglés y en español. El botón **EN / ES** de la cabecera
cambia el idioma (queda guardado en una cookie); en la primera visita se usa el
idioma del navegador.

- Los textos se escriben en inglés con `{% translate %}` / `gettext`, y la
  traducción al español está en `locale/es/LC_MESSAGES/django.po`.
- El archivo compilado `django.mo` está en el repositorio, así que no hace
  falta instalar nada para ver la app en español.
- Si agregas o cambias un texto: `python manage.py makemessages -l es`, traduce
  el texto nuevo en el `.po` y luego `python manage.py compilemessages`. Estos
  dos comandos necesitan GNU gettext instalado.
- Las categorías tienen nombre en inglés y en español (`name_en`, `name_es`).
  Las conocidas se llenan solas; las demás se traducen desde el admin.
- Los precios se muestran en pesos sin decimales: `$85,000` en inglés y
  `$85.000` en español.

## Pruebas

`python manage.py test` corre todas las pruebas. Cada push y cada Pull Request
las corre también en GitHub Actions (`.github/workflows/ci.yml`) contra
PostgreSQL, la misma base de datos de producción.

## Seguridad

- **Secretos:** las llaves y contraseñas van en `.env` (o en las variables de
  entorno del servidor), nunca en el repositorio.
- **Usuarios administradores:** se crean con `python manage.py createsuperuser`.
  No hay usuarios ni contraseñas por defecto. `seed_events` crea los
  organizadores de ejemplo sin contraseña (no pueden iniciar sesión) y, si
  encuentra los que versiones anteriores creaban con una contraseña conocida,
  les quita la contraseña y el acceso de administrador.
- **Producción:** `DEBUG` está apagado por defecto y el proyecto no arranca sin
  `DJANGO_SECRET_KEY`. Con `DJANGO_HTTPS=True` se activan las cookies seguras,
  HSTS y la redirección a HTTPS.
- **Formularios públicos:** el inicio de sesión, el registro, la propuesta de
  eventos y la recuperación de contraseña tienen límite de intentos por
  visitante (`doday/ratelimit.py`); el registro y la propuesta tienen además
  un campo trampa contra bots.
- **Recuperar contraseña:** enlace "¿Olvidaste tu contraseña?" en el inicio de
  sesión; el enlace llega por correo y vence solo.
