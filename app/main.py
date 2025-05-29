from flask import Flask, jsonify, request, Response
from flask_jwt_extended import JWTManager, jwt_required
from flasgger import Swagger
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from app.data import BOMBEROS_DATA
from app.utils import filter_bomberos, filter_by_coords
from app.auth import auth_bp
import os
import csv
import logging

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec_1',
            "route": '/apispec_1.json',
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\""
        }
    },
    "security": [{"Bearer": []}]
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "API Bomberos de Chile",
        "description": """
La **API Bomberos de Chile** entrega información actualizada y centralizada sobre todos los Cuerpos de Bomberos a lo largo del país.

**¿Qué puedes consultar con esta API?**

- **Buscar Cuerpos de Bomberos** por nombre, región, comuna, o ID.
- **Obtener datos de contacto** de un cuerpo específico.
- **Filtrar cuerpos por coordenadas geográficas** y radio de búsqueda.
- **Encontrar el cuerpo de bomberos más cercano** a una ubicación.
- **Listar comunas y regiones disponibles** en el dataset.
- **Saber qué comunas atiende cada Cuerpo de Bomberos**.
- **Listar los cuerpos que cubren una comuna específica**.
- **Estadísticas**: cantidad total y detalle de cuerpos por región o provincia.
- **Exportar** todos los datos en formato JSON o CSV.
- **Autenticación JWT**: Todos los endpoints están protegidos por token JWT (excepto `/login`).

**Uso típico:**
El sistema permite integrar información relevante para aplicaciones municipales, sistemas de despacho de emergencias, estudios territoriales, y plataformas ciudadanas.

**¿Qué información entrega cada cuerpo de bomberos?**
- ID único
- Nombre oficial
- Región, provincia y comuna
- Dirección física
- Teléfonos de contacto
- Comunas atendidas
- Coordenadas geográficas (latitud/longitud)
- Código CUT (clave única territorial)

**¿Cómo acceder?**
1. Realiza login con tus credenciales (`/login`) para obtener un token JWT.
2. Usa el token en el header de autorización para consumir los demás endpoints.

**Documentación protegida:**
El acceso a `/apidocs` requiere autenticación básica adicional.

---
""",
        "version": "0.0.1",
        "contact": {
            "name": "Proyecto API Bomberos de Chile",
            "url": "https://github.com/matiasua/api-bomberos-cl",  # Cambia por tu url real si tienes
            "email": "contacto@m4s.cl"
        },
        "license": {
            "name": "MIT License"
        }
    },
    "host": "localhost:5000",
    "basePath": "/",
    "schemes": [
        "http"
    ]
}

def check_auth(username, password):
    return username == os.environ.get("DOCS_USER", "docuser") and password == os.environ.get("DOCS_PASS", "docpass")

def authenticate():
    return Response(
    'Autenticación requerida.', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_basic_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def create_app():
    app = Flask(__name__)
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'super-secret-key')
    app.config['SWAGGER'] = {'title': 'API Bomberos de Chile', 'uiversion': 3}
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    Swagger(app, template=swagger_template, config=swagger_config)
    JWTManager(app)

    # Inicializar Limiter en el objeto app
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[]
    )
    app.register_blueprint(auth_bp)
    limiter.limit("5 per minute")(app.view_functions['auth.login'])

    # Proteger solo la ruta de /apidocs
    @app.before_request
    def protect_apidocs():
        if request.path.startswith("/apidocs"):
            return requires_basic_auth(lambda: None)()

    @app.route('/regiones', methods=['GET'])
    @jwt_required()
    def get_regiones():
        """
        Listar todas las regiones con cuerpos de bomberos disponibles
        ---
        tags:
          - catalogos
        security:
          - Bearer: []
        responses:
          200:
            description: Lista de regiones
        """
        regiones = sorted(set([b["region"] for b in BOMBEROS_DATA]))
        return jsonify(regiones)

    @app.route('/comunas', methods=['GET'])
    @jwt_required()
    def get_comunas():
        """
        Listar comunas, filtrado por región si se envía como parámetro
        ---
        tags:
          - catalogos
        security:
          - Bearer: []
        parameters:
          - in: query
            name: region
            type: string
            required: false
            description: Región a filtrar
        responses:
          200:
            description: Lista de comunas
        """
        region = request.args.get("region")
        if region:
            comunas = sorted(set([b["comuna"] for b in BOMBEROS_DATA if b["region"].lower() == region.lower()]))
        else:
            comunas = sorted(set([b["comuna"] for b in BOMBEROS_DATA]))
        return jsonify(comunas)


    @app.route('/bomberos/closest', methods=['GET'])
    @jwt_required()
    def get_bombero_cercano():
        """
        Obtener el cuerpo de bomberos más cercano a las coordenadas dadas
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: query
            name: lat
            type: number
            required: true
          - in: query
            name: lon
            type: number
            required: true
        responses:
          200:
            description: Cuerpo de bomberos más cercano
          400:
            description: Parámetros faltantes o inválidos
        """
        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except Exception:
            return jsonify({"msg": "Parámetros inválidos"}), 400
        from geopy.distance import geodesic
        min_dist = float("inf")
        closest = None
        for b in BOMBEROS_DATA:
            dist = geodesic((lat, lon), (b["latitud"], b["longitud"])).km
            if dist < min_dist:
                min_dist = dist
                closest = b
        if closest:
            return jsonify({"dist_km": min_dist, "bombero": closest})
        else:
            return jsonify({"msg": "No se encontraron datos"}), 404



    @app.route('/estadisticas/regiones', methods=['GET'])
    @jwt_required()
    def estadisticas_regiones():
        """
        Obtener resumen de cuerpos de bomberos por región (total y listado)
        ---
        tags:
          - estadisticas
        security:
          - Bearer: []
        responses:
          200:
            description: Estadísticas por región
        """
        regiones = {}
        for b in BOMBEROS_DATA:
            r = b["region"]
            if r not in regiones:
                regiones[r] = []
            regiones[r].append(b)
        resultado = []
        for region, cuerpos in regiones.items():
            resultado.append({
                "region": region,
                "total": len(cuerpos),
                "cuerpos": cuerpos
            })
        return jsonify(resultado)

    @app.route('/estadisticas/provincias', methods=['GET'])
    @jwt_required()
    def estadisticas_provincias():
        """
        Obtener resumen de cuerpos de bomberos por provincia (total y listado)
        ---
        tags:
          - estadisticas
        security:
          - Bearer: []
        responses:
          200:
            description: Estadísticas por provincia
        """
        provincias = {}
        for b in BOMBEROS_DATA:
            p = b.get("provincia", "Desconocida")
            if p not in provincias:
                provincias[p] = []
            provincias[p].append(b)
        resultado = []
        for provincia, cuerpos in provincias.items():
            resultado.append({
                "provincia": provincia,
                "total": len(cuerpos),
                "cuerpos": cuerpos
            })
        return jsonify(resultado)

    @app.route('/bomberos/<int:id>/comunas-atendidas', methods=['GET'])
    @jwt_required()
    def comunas_atendidas(id):
        """
        Listar comunas atendidas por un cuerpo de bomberos
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: path
            name: id
            type: integer
            required: true
        responses:
          200:
            description: Lista de comunas atendidas
          404:
            description: No encontrado
        """
        b = next((b for b in BOMBEROS_DATA if b["id"] == id), None)
        if not b:
            return jsonify({"msg": "No encontrado"}), 404
        # Si comunasAtendidas es string separada por coma, dividir
        comunas = [c.strip() for c in b.get("comunasAtendidas", "").split(",") if c.strip()]
        return jsonify({"comunasAtendidas": comunas})

    @app.route('/bomberos/<int:id>/contacto', methods=['GET'])
    @jwt_required()
    def contacto_bombero(id):
        """
        Obtener información de contacto de un cuerpo de bomberos
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: path
            name: id
            type: integer
            required: true
        responses:
          200:
            description: Datos de contacto
          404:
            description: No encontrado
        """
        b = next((b for b in BOMBEROS_DATA if b["id"] == id), None)
        if not b:
            return jsonify({"msg": "No encontrado"}), 404
        contacto = {
            "nombre": b["nombre"],
            "direccion": b["direccion"],
            "telefono": b["telefono"]
        }
        return jsonify(contacto)

    @app.route('/bomberos/cobertura', methods=['GET'])
    @jwt_required()
    def cobertura_comuna():
        """
        Listar cuerpos de bomberos que atienden una comuna específica
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: query
            name: comuna
            type: string
            required: true
            description: Nombre de la comuna
        responses:
          200:
            description: Cuerpos que cubren la comuna
        """
        comuna = request.args.get("comuna", "").strip().lower()
        if not comuna:
            return jsonify({"msg": "Debe especificar la comuna"}), 400
        resultados = [b for b in BOMBEROS_DATA if comuna in b.get("comunasAtendidas", "").lower()]
        return jsonify(resultados)

    @app.route('/bomberos/export/json', methods=['GET'])
    @jwt_required()
    def export_json():
        """
        Exportar listado completo de cuerpos de bomberos en formato JSON
        ---
        tags:
          - export
        security:
          - Bearer: []
        responses:
          200:
            description: Archivo JSON
        """
        return jsonify(BOMBEROS_DATA)

    @app.route('/bomberos/export/csv', methods=['GET'])
    @jwt_required()
    def export_csv():
        """
        Exportar listado completo de cuerpos de bomberos en formato CSV
        ---
        tags:
          - export
        security:
          - Bearer: []
        responses:
          200:
            description: Archivo CSV
        """
        if not BOMBEROS_DATA:
            return Response("", mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=bomberos.csv"})
        fieldnames = list(BOMBEROS_DATA[0].keys())
        output = ",".join(fieldnames) + "\n"
        for row in BOMBEROS_DATA:
            output += ",".join([str(row.get(fn, "")) for fn in fieldnames]) + "\n"
        return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=bomberos.csv"})



    @app.route('/bomberos', methods=['GET'])
    @jwt_required()
    def get_bomberos():
        """
        Listar o buscar cuerpos de bomberos
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: query
            name: id
            type: integer
          - in: query
            name: nombre
            type: string
          - in: query
            name: comuna
            type: string
          - in: query
            name: region
            type: string
        responses:
          200:
            description: Lista de cuerpos de bomberos
        """
        filtros = {
            "id": request.args.get("id"),
            "nombre": request.args.get("nombre"),
            "comuna": request.args.get("comuna"),
            "region": request.args.get("region"),
        }
        results = filter_bomberos(BOMBEROS_DATA, **{k: v for k, v in filtros.items() if v})
        return jsonify(results)

    @app.route('/bomberos/<int:id>', methods=['GET'])
    @jwt_required()
    def get_bombero_id(id):
        """
        Buscar cuerpo de bomberos por ID
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: path
            name: id
            type: integer
            required: true
        responses:
          200:
            description: Cuerpo encontrado
          404:
            description: No encontrado
        """
        item = next((b for b in BOMBEROS_DATA if b["id"] == id), None)
        if not item:
            return jsonify({"msg": "No encontrado"}), 404
        return jsonify(item)

    @app.route('/bomberos/nearby', methods=['GET'])
    @jwt_required()
    def get_bomberos_nearby():
        """
        Buscar cuerpos de bomberos cercanos a una coordenada y radio
        ---
        tags:
          - bomberos
        security:
          - Bearer: []
        parameters:
          - in: query
            name: lat
            type: number
            required: true
          - in: query
            name: lon
            type: number
            required: true
          - in: query
            name: radio
            type: number
            required: true
            description: Radio en kilómetros
        responses:
          200:
            description: Lista de cuerpos cercanos
          400:
            description: Faltan parámetros
        """
        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
            radio = float(request.args["radio"])
        except Exception:
            return jsonify({"msg": "Parámetros inválidos"}), 400
        results = filter_by_coords(BOMBEROS_DATA, lat, lon, radio)
        return jsonify(results)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"msg": "No encontrado"}), 404

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"msg": "No autorizado"}), 401

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0")
