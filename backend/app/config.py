import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
)
print("SECRET_KEY:", SECRET_KEY)
print("ALGORITHM:", ALGORITHM)
print("ACCESS_TOKEN_EXPIRE_MINUTES:", ACCESS_TOKEN_EXPIRE_MINUTES)
