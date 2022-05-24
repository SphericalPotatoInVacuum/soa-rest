import os
import struct
from random import randint, random
from typing import Optional

import pdfkit
import pika
from jinja2 import Template
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)

    name = Column(String(200))
    avatar = Column(String(os.pathconf('/', 'PC_PATH_MAX')))
    gender = Column(String(200))
    username = Column(String(200))

    games_won = Column(Integer)
    games_lost = Column(Integer)
    total_time = Column(Float)

    pwd_hash = Column(String(128))

    def __init__(self,
                 username: str,
                 pwd_hash: str,
                 name: Optional[str] = None,
                 avatar: Optional[str] = None,
                 gender: Optional[str] = None):
        self.name = name
        self.username = username
        self.pwd_hash = pwd_hash
        self.avatar = avatar
        self.gender = gender

        self.games_won = randint(0, 100)
        self.games_lost = randint(0, 100)
        self.total_time = sum([random() * 1 + 0.5 for _ in range(self.games_won + self.games_lost)])

    def __repr__(self) -> str:
        return f'<User name={self.name}, avatar={self.avatar}, gender={self.gender}, username={self.username}'


engine = create_engine("postgresql://username:password@database/database", echo=True, future=True)
session = Session(engine)

connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()
channel.queue_declare(queue='request', durable=True)
channel.queue_declare(queue='response', durable=True)


def callback(ch, method, properties, body):
    user_id, request_id = struct.unpack('Q32s', body)

    with open('template.html.jinja2', 'r') as file:
        template = Template(file.read())

    user: User = session.query(User).filter_by(id=user_id).first()
    if user.avatar is not None:
        avatar = f'http://server:5000/web/avatars/{user.username}'
    else:
        avatar = 'https://cdn.pixabay.com/photo/2016/08/08/09/17/avatar-1577909_1280.png'

    html = template.render(wlRatio=f'{(user.games_won / (user.games_lost + user.games_won) * 100):.1f}',
                           avatar=avatar,
                           username=user.username,
                           name=(user.name or 'unknown'),
                           gender=(user.gender or 'unknown'),
                           games_played=(user.games_lost + user.games_won),
                           game_time=f'{user.total_time: .1f}',
                           wins=user.games_won)
    pdfkit.from_string(
        html,
        f'{request_id.decode()}.pdf',
        options={
            'margin-top': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'margin-right': '0'})
    with open(f'{request_id.decode()}.pdf', 'rb') as pdf:
        content = pdf.read()
        header = request_id
        body = header + content
        ch.basic_publish(
            exchange='',
            routing_key='response',
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )

    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='request', on_message_callback=callback)
channel.start_consuming()
