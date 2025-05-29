from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
import os

auth_bp = Blueprint('auth', __name__)

USERS = {
    os.environ.get("ADMIN_USER", "admin"): os.environ.get("ADMIN_PASS", "admin123")
}

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login para obtener token JWT
    ---
    tags:
      - auth
    parameters:
      - in: body
        name: body
        schema:
          required:
            - username
            - password
          properties:
            username:
              type: string
            password:
              type: string
    responses:
      200:
        description: Token generado
        examples:
          application/json:
            {
              "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci..."
            }
      401:
        description: Credenciales inválidas
        examples:
          application/json:
            {
              "msg": "Credenciales inválidas"
            }
    """
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if USERS.get(username) == password:
        token = create_access_token(identity=username)
        return jsonify(access_token=token), 200
    return jsonify({"msg": "Credenciales inválidas"}), 401
