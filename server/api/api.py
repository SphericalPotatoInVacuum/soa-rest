import base64
import datetime
from functools import wraps
import json
from pathlib import Path
import uuid

import jwt
from flask import Flask, jsonify, make_response, request, send_file
from flask_marshmallow import Marshmallow
from flask_restx import Api, Resource, reqparse
from flask_sqlalchemy import SQLAlchemy
from loguru import logger
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.datastructures import FileStorage
import pika
import struct

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@database/database'
app.config['SECRET_KEY'] = '8fbeef5e458c6244f700f1e274b59557dbb3703bd609577d71a474c08853c86f'
SAVE_PATH = Path('/server/user_pics')
SAVE_PATH.mkdir(exist_ok=True)
db = SQLAlchemy(app)
ma = Marshmallow(app)
api = Api(app)

connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()
channel.queue_declare(queue='request', durable=True)
channel.queue_declare(queue='response', durable=True)
connection.close()

stats = {}


def create_app() -> Flask:
    from api.models import User, user_schema, user_schemas

    def token_required(f):
        @wraps(f)
        def decorator(*args, **kwargs):
            token = None
            if 'Authorization' in request.headers:
                header = request.headers['Authorization']
                if header.startswith('Bearer '):
                    token = header.split()[1]

            if not token:
                return jsonify({'message': 'a valid token is missing'})
            try:
                data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                current_user = User.query.filter_by(id=data['id']).first()
            except BaseException as e:
                return jsonify({'message': 'token is invalid'})

            return f(current_user, *args, **kwargs)
        return decorator

    db.create_all()
    session = db.session

    @api.route('/api/register')
    class RegisterResource(Resource):
        def post(self):
            parser = reqparse.RequestParser()
            parser.add_argument('username', type=str)
            parser.add_argument('password', type=str)
            data = parser.parse_args(strict=True)

            user = User.query.filter_by(username=data['username']).first()
            if user is not None:
                return {'error': f'User with username {data["username"]} already exists!'}, 400

            hashed_password = generate_password_hash(data['password'], method='sha256')
            new_user = User(username=data['username'], pwd_hash=hashed_password)
            session.add(new_user)
            session.commit()

            return {'message': 'registration successful'}

    @api.route('/api/login')
    class LoginResource(Resource):
        def post(self):
            parser = reqparse.RequestParser()
            parser.add_argument('username', type=str)
            parser.add_argument('password', type=str)
            data = parser.parse_args(strict=True)

            user: User = User.query.filter_by(username=data['username']).first()
            if user is None or not check_password_hash(user.pwd_hash, data['password']):
                return {'error': 'Invalid credentials'}, 400

            token = jwt.encode({'id': user.id, 'exp': datetime.datetime.utcnow() +
                               datetime.timedelta(minutes=45)}, app.config['SECRET_KEY'], 'HS256')
            return jsonify({'token': token})

    @api.route('/api/users')
    class UserResourse(Resource):
        def get(self):
            parser = reqparse.RequestParser()
            parser.add_argument('usernames', type=list, location='json')
            data = parser.parse_args(strict=True)
            usernames = data['usernames']

            users = User.query.filter(User.username.in_(usernames)).all()
            rets = user_schemas.dump(users)

            return rets

        @token_required
        def put(current_user: User, self):
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str)
            parser.add_argument('avatar', type=str)
            parser.add_argument('gender', type=str)

            data = parser.parse_args()

            if data['name'] is not None:
                current_user.name = data['name']
            if data['avatar'] is not None:
                current_user.username = data['avatar']
            if data['gender'] is not None:
                current_user.gender = data['gender']

            session.commit()

            return user_schema.dump(current_user)

    @api.route('/api/upload_avatar')
    class UploadResource(Resource):
        @token_required
        def post(current_user: User, self):
            parser = reqparse.RequestParser()
            parser.add_argument('avatar', type=FileStorage, location='files', required=True)

            data = parser.parse_args()
            avatar: FileStorage = data['avatar']
            save_path = Path(str(current_user.id)).with_suffix(Path(avatar.filename).suffix)
            avatar.save(SAVE_PATH / save_path)

            current_user.avatar = str(save_path)
            session.commit()

            return {'message': 'success'}

    @app.route('/web/avatars/<username>')
    def get_username(username):
        user = User.query.filter_by(username=username).first()
        if user is None:
            return {'error': 'No such user'}
        return send_file(SAVE_PATH / Path(user.avatar))

    @api.route('/api/statistics/')
    class StatsResource(Resource):
        def post(self):
            parser = reqparse.RequestParser()
            parser.add_argument('username', type=str, required=True)
            data = parser.parse_args()
            username = data['username']

            user = User.query.filter_by(username=username).first()
            if user is None:
                return {'error': 'No such user'}, 400

            data = request.get_json(force=True)
            request_id = uuid.uuid4().hex
            body = struct.pack('Q32s', user.id, request_id.encode())

            connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
            channel = connection.channel()
            channel.confirm_delivery()

            while True:
                try:
                    channel.basic_publish(
                        exchange='',
                        routing_key='request',
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=2
                        )
                    )
                    connection.close()
                    return {'request_id': request_id}
                except pika.exceptions.UnroutableError:
                    continue

        def get(self):
            parser = reqparse.RequestParser()
            parser.add_argument('request_id', type=str, required=True)
            data = parser.parse_args()
            request_id = data['request_id']

            connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
            channel = connection.channel()
            while True:
                method, properties, body = channel.basic_get(queue='response')
                if method is None:
                    break
                request_id = body[:32]
                content = body[32:]
                stats[request_id] = content
                channel.basic_ack(delivery_tag=method.delivery_tag)
            connection.close()

            if request_id in stats:
                response = make_response(stats[request_id])
                response.headers['content-type'] = 'application/octet-stream'
                return response
            return {'error': 'this statistics is not ready yet'}, 400

    return app
