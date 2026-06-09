from dotenv import dotenv_values

config = dotenv_values(".env")

SQLALCHEMY_DATABASE_URL = config["SQLALCHEMY_DATABASE_URL"]
SECRET_KEY = config["SECRET_KEY"]
ACCESS_TOKEN_EXPIRE_MINUTES = config["ACCESS_TOKEN_EXPIRE_MINUTES"]
REDIS_URL = config["REDIS_URL"]
ALGORITHM = "HS256"