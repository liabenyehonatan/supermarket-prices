# app/db/base.py

# SQLAlchemy is the library that lets us define database tables as Python classes.
# Instead of writing raw SQL like CREATE TABLE, we write Python classes and
# SQLAlchemy translates them to SQL for us automatically.
from sqlalchemy.orm import DeclarativeBase

# DeclarativeBase is the "parent class" that every table class will inherit from.
# Think of it as a template that gives all your tables superpowers —
# like knowing how to talk to the database.
class Base(DeclarativeBase):
    pass