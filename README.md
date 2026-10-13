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
   - `GOOGLE_MAPS_API_KEY`: habilita el cálculo de distancia/tiempo de tránsito
     (REQ-01/REQ-03, Navigation). Sin ella, ese dato simplemente no se muestra.
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

- **events**: catálogo de eventos — CRUD, detalle, favoritos, ticketing
  (REQ-02, REQ-04, REQ-05, REQ-06, REQ-16, REQ-17, REQ-18, REQ-21).
- **search**: filtros sobre el catálogo de eventos — palabra clave, categoría,
  rango de fechas, solo gratuitos, limpiar filtros (REQ-07, REQ-11, REQ-19,
  REQ-20, REQ-22). No tiene tablas propias, solo consulta `events.Event`.
- **navigation**: ubicación de alojamiento y cálculo de ruta/distancia al
  evento (REQ-01, REQ-03), validando la frontera geográfica (REQ-26).
- El listado de eventos incluye mapa Leaflet en vista dividida y un botón para
  cambiar a mapa de pantalla completa (REQ-27).

Correr las pruebas de todas las apps:

- `python manage.py test`

Super usuarios:
usuario: Sebas. contraseña: 123456789.
usuario: maria. contraseña: 123456789.
