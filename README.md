## Running the server locally

1. clonar el repo o descargar:
   git clone https://github.com/JANATAROTO/Doday-Project.git
   cd Doday-Project
   
2. crear el ambiente virtual:
   python -m venv venv
   source venv/bin/activate o venv\Scripts\activate
   
3. instalar las dependencias:
   pip install -r requirements.txt
   
4. (opcional) variables de entorno — si no se definen, el proyecto corre igual
   con valores de desarrollo por defecto:
   - `DJANGO_SECRET_KEY`: clave secreta para producción.
   - `DJANGO_DEBUG`: `True`/`False` (por defecto `True`).
   - `GOOGLE_MAPS_API_KEY`: habilita el cálculo de distancia/tiempo de tránsito
     (REQ-01/REQ-03, Navigation). Sin ella, ese dato simplemente no se muestra.

5. migraciones de la base de datos:
   python manage.py migrate
   
6. semilla para eventos en la base de datos:
   python manage.py seed_events
   
7. lanzar el servidor:
   python manage.py runserver
   
8. abrir http://127.0.0.1:8000/ o el que salga.

## Estructura del proyecto

El código está organizado en tres apps de Django que corresponden a los
componentes del Component Diagram (ver la Wiki, Entregable 2):

- **events**: catálogo de eventos — CRUD, detalle, favoritos, ticketing
  (REQ-02, REQ-04, REQ-05, REQ-06, REQ-16, REQ-17, REQ-18, REQ-21).
- **search**: filtros sobre el catálogo de eventos — palabra clave, categoría,
  rango de fechas, solo gratuitos, limpiar filtros (REQ-07, REQ-11, REQ-19,
  REQ-20, REQ-22). No tiene tablas propias, solo consulta `events.Event`.
- **navigation**: ubicación de alojamiento y cálculo de ruta/distancia al
  evento (REQ-01, REQ-03).

Correr las pruebas de todas las apps:

   python manage.py test
