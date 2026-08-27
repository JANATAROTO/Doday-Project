## Running the server locally

1. clonar el repo o descargar:
   git clone https://github.com/JANATAROTO/Doday-Project.git
   cd Doday-Project
   
2. crear el ambiente virtual:
   python -m venv venv
   source venv/bin/activate o venv\Scripts\activate
   
3. instalar las dependencias:
   pip install -r requirements.txt
   
4. migraciones de la base de datos:
   python manage.py migrate
   
5. semilla para eventos en la base de datos:
   python manage.py seed_events
   
6. lanzar el servidor:
   python manage.py runserver
   
7. abrir http://127.0.0.1:8000/ o el que salga.
