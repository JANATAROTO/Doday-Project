## Running the server locally

1. clonar el repo o descargar:
   - `git clone https://github.com/JANATAROTO/Doday-Project.git`
   - `cd Doday-Project`

2. crear el ambiente virtual:
   - `python -m venv venv`
   - activar el ambiente virtual:
     - Windows: `venv\Scripts\activate`
     - Linux/macOS: `source venv/bin/activate`

3. instalar las dependencias:
   - `pip install -r requirements.txt`

4. crear el archivo de configuración local (no se sube al repositorio):
   - Windows: `copy .env.example .env`
   - Linux/macOS: `cp .env.example .env`

   El archivo `.env` ya trae `DJANGO_DEBUG=True`, que es lo único necesario
   para correr en local. Sin ese archivo el proyecto no arranca: por seguridad
   `DEBUG` viene apagado y exige una `DJANGO_SECRET_KEY`. Las demás variables
   son opcionales y están explicadas en `.env.example`:
   - `GOOGLE_MAPS_API_KEY`: mapa interactivo de eventos (Maps JavaScript API).
     Sin ella, `/map/` muestra un aviso en vez del mapa. La llave debe estar
     restringida a los sitios donde corre la app.
   - `ORS_API_KEY`: distancia, tiempo y ruta al evento (OpenRouteService).
   - `TICKETMASTER_API_KEY`: sincronización de eventos externos.
   - `ACCOMMODATION_ALLOWED_BOUNDS`: frontera `sur,norte,oeste,este` para
     validar alojamientos. Por defecto, una caja aproximada de Medellín.
   - `EMAIL_HOST` y relacionadas: envío de correos (recuperar contraseña).
     Sin ellas, los correos se imprimen en la consola del servidor.

5. migraciones de la base de datos:
   - `python manage.py migrate`

6. semilla para eventos en la base de datos:
   - `python manage.py seed_events`

7. sincronizar eventos externos:
   - `python manage.py sync_external_events --city "Medellín" --size 50`
   - Este comando es idempotente y puede programarse cada cierto tiempo con el
     Task Scheduler de Windows o cron; la clave externa evita duplicados.

8. lanzar el servidor:
   - `python manage.py runserver`

9. abrir http://127.0.0.1:8000/ o el que salga.

## Despliegue en AWS Academy (EC2)

Pasos para poner en el servidor la última versión de `main`:

1. Entrar a la instancia y actualizar el código:
   - `cd Doday-Project && git pull origin main`
   - `source venv/bin/activate && pip install -r requirements.txt`
2. Crear o actualizar `api_key.env` en la raíz del proyecto (no se sube al
   repositorio). Además de las llaves de las APIs, debe incluir la IP pública
   o el dominio del servidor; sin eso Django responde *400 Bad Request*:

   ```
   DJANGO_ALLOWED_HOSTS=<IP-publica>,localhost,127.0.0.1
   DJANGO_SECRET_KEY=<una clave larga y secreta>   # obligatoria en producción
   GOOGLE_MAPS_API_KEY=...
   ORS_API_KEY=...
   TICKETMASTER_API_KEY=...
   ```
3. Aplicar las migraciones (la versión final agrega tablas y columnas):
   - `python manage.py migrate`
   - opcional, solo si la base está vacía: `python manage.py seed_events` y
     `python manage.py createsuperuser`
4. Levantar el servidor escuchando en todas las interfaces:
   - `python manage.py runserver 0.0.0.0:8000`
   - En el *Security Group* de la instancia debe estar abierto el puerto 8000
     (o el 80 si se usa Nginx).
5. En Google Cloud Console, agregar `http://<IP-publica>:8000/*` a las
   restricciones de sitio web de la llave de Google Maps; si no, el mapa
   muestra el aviso "El mapa no se pudo cargar".
6. Si la IP pública cambia al reiniciar el laboratorio, actualizar
   `DJANGO_ALLOWED_HOSTS` y la restricción de la llave de Google.

Con `DJANGO_DEBUG=False` hay que correr `python manage.py collectstatic` y
servir la carpeta `staticfiles/` con un servidor web como Nginx; con el valor
por defecto (`True`) `runserver` sirve los estilos por sí mismo.

## Estructura del proyecto

El código está organizado en tres apps de Django que corresponden a los
componentes del Component Diagram (ver la Wiki, Entregable 2):

- **events**: catálogo de eventos — CRUD, detalle, favoritos, share link,
  ticketing y link externo a Google Maps (REQ-02, REQ-04, REQ-05, REQ-06,
  REQ-15, REQ-16, REQ-17, REQ-18, REQ-21).
- **search**: filtros sobre el catálogo de eventos — palabra clave, categoría,
  rango de fechas, solo gratuitos, limpiar filtros (REQ-07, REQ-11, REQ-19,
  REQ-20, REQ-22). No tiene tablas propias, solo consulta `events.Event`.
- **navigation**: ubicación de alojamiento validando la frontera geográfica
  (REQ-26), cálculo de ruta/distancia al evento (REQ-01, REQ-03) y mapa
  interactivo de eventos filtrados con preview al hacer clic en un marcador
  (REQ-09, REQ-10).
- El listado de eventos incluye mapa Leaflet en vista dividida y un botón para
  cambiar a mapa de pantalla completa (REQ-27).
- **events** también recibe las propuestas de eventos de la comunidad con el
  formulario público "Proponer un evento" (REQ-24) y la pantalla de
  moderación del personal para aprobarlas o rechazarlas (REQ-25). Solo los
  eventos aprobados aparecen en el catálogo, la búsqueda, el mapa y favoritos.
- **analytics**: registra de forma anónima las vistas de eventos, los
  favoritos y los clics en "Comprar boletas", y muestra al personal un panel
  en `/analytics/` con eventos más vistos, interés por categoría, actividad
  por día de la semana y oferta próxima (REQ-30).
  - Para una demostración con datos simulados:
    `python manage.py generate_demo_interactions --days 30` (agrega
    `--clear` para borrar antes las interacciones existentes). Úsalo solo en
    una base de datos de demostración.

## Idiomas (REQ-29)

La interfaz está en inglés y en español. El botón **EN / ES** de la cabecera
cambia el idioma (queda guardado en una cookie); en la primera visita se usa el
idioma del navegador, así que un residente con el navegador en español ve la
app en español y un visitante extranjero la ve en inglés.

- Los textos del código y las plantillas se escriben en inglés con
  `{% translate %}` / `gettext`, y la traducción al español está en
  `locale/es/LC_MESSAGES/django.po`.
- El archivo compilado `django.mo` está en el repositorio, así que no hace
  falta instalar nada para ver la app en español.
- Si agregas o cambias un texto: `python manage.py makemessages -l es`, traduce
  el texto nuevo en el `.po` y luego `python manage.py compilemessages`. Estos
  dos comandos necesitan GNU gettext instalado.
- Las categorías tienen nombre en inglés y en español (`name_en`, `name_es`).
  Las conocidas (Música, Sports, Teatro...) se llenan solas; las demás se
  pueden traducir desde el admin.
- Los precios se muestran en pesos sin decimales: `$85,000` en inglés y
  `$85.000` en español.

Correr las pruebas de todas las apps:

- `python manage.py test`

Cada push y cada Pull Request corre estas mismas pruebas en GitHub Actions
(`.github/workflows/ci.yml`).

## Seguridad

- **Secretos:** las llaves y contraseñas van en `.env` (o en las variables de
  entorno del servidor), nunca en el repositorio. `.env.example` lista las
  variables sin valores.
- **Usuarios administradores:** se crean con `python manage.py createsuperuser`.
  No hay usuarios ni contraseñas por defecto. `seed_events` crea los
  organizadores de ejemplo sin contraseña (no pueden iniciar sesión) y, si
  encuentra los que versiones anteriores creaban con una contraseña conocida,
  les quita la contraseña y el acceso de administrador.
- **Producción:** `DEBUG` está apagado por defecto y el proyecto no arranca sin
  `DJANGO_SECRET_KEY`. Con `DJANGO_HTTPS=True` se activan las cookies seguras,
  HSTS y la redirección a HTTPS.
- **Formularios públicos:** el inicio de sesión, el registro, la propuesta de
  eventos y la recuperación de contraseña tienen límite de intentos por IP
  (`doday/ratelimit.py`); el registro y la propuesta tienen además un campo
  trampa contra bots.
- **Recuperar contraseña:** enlace "¿Olvidaste tu contraseña?" en el inicio de
  sesión; el enlace llega por correo y vence solo.
