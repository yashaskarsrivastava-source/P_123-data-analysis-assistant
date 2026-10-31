from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from .db import Base
now = lambda: datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    created = Column(DateTime, default=now)

class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    path = Column(String)
    profile = Column(JSON)
    created = Column(DateTime, default=now)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    title = Column(String, default="New chat")
    created = Column(DateTime, default=now)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String)
    content = Column(Text)
    result = Column(JSON)
    created = Column(DateTime, default=now)
