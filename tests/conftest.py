import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, get_db
from backend.main import app
from backend.rate_limiter import rate_limiter

# Dedicated test database to ensure production/local database is NEVER touched
TEST_DB_URL = "sqlite:///./test_expense_tracker.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def clean_test_db():
    rate_limiter.requests.clear()
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    rate_limiter.requests.clear()
