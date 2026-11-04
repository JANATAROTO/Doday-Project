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

4. (opcional) variables de entorno — si no se definen, el proyecto corre igual
   con valores de desarrollo por defecto:
   - `DJANGO_SECRET_KEY`: clave secreta para producción.
   - `DJANGO_DEBUG`: `True`/`False` (por defecto `True`).
   - `GOOGLE_MAPS_API_KEY`: habilita el mapa interactivo de eventos (REQ-09/
     REQ-10, Navigation, Maps JavaScript API). Sin ella, la página `/map/`
     muestra un aviso en vez del mapa. Necesita la "Maps JavaScript API"
     habilitada en Google Cloud Console.
   - `ORS_API_KEY`: habilita el cálculo de distancia/tiempo de tránsito al
     evento (REQ-01/REQ-03, Navigation, OpenRouteService). Sin ella, ese dato
     simplemente no se muestra. Es un proveedor distinto a Google Maps.
   - `TICKETMASTER_API_KEY`: habilita la sincronización de eventos externos
     (REQ-13).
   - `ACCOMMODATION_ALLOWED_BOUNDS`: frontera `sur,norte,oeste,este` para
     validar alojamientos (REQ-26). Por defecto usa una caja aproximada de
     Medellín: `6.10,6.40,-75.70,-75.45`.

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

Super usuarios:
usuario: Sebas. contraseña: 123456789.
usuario: maria. contraseña: 123456789.
