import os
from random import randint, random
from typing import Optional
from api.api import db, ma
import enum


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200))
    avatar = db.Column(db.String(os.pathconf('/', 'PC_PATH_MAX')))
    gender = db.Column(db.String(200))
    username = db.Column(db.String(200))

    games_won = db.Column(db.Integer)
    games_lost = db.Column(db.Integer)
    total_time = db.Column(db.Float)

    pwd_hash = db.Column(db.String(128))

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


class UserSchema(ma.Schema):
    class Meta:
        fields = ('name', 'avatar', 'gender', 'username')
        model = User


user_schema = UserSchema()
user_schemas = UserSchema(many=True)
