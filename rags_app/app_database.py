from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

SQLALCHEMY_DATABASE_URL = f'sqlite:///{os.environ["RAGS_HOME"]}/projects/rags_database.db'
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


TEST_DATABASE_LOCATION = f'{os.environ["RAGS_HOME"]}/projects/rags_test_database.db'
SQLALCHEMY_TEST_DATABASE_URL = f'sqlite:///{TEST_DATABASE_LOCATION}'
test_database_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_database_engine)


Base = declarative_base()
