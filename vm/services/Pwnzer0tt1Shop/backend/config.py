
import os

DOCKER = os.getenv("DOCKER", "0") == "1"

SECRET_KEY = os.getenv('SECRET_KEY', 'https://www.youtube.com/watch?v=L8XbI9aJOXk')

TOKEN_SECRET_LEN = int(os.getenv('TOKEN_SECRET_LEN', 16))

TOKEN_SECRET = os.getenv('TOKEN_SECRET', 'https://www.youtube.com/shorts/PYOuZw1c4ZU').ljust(TOKEN_SECRET_LEN, 'A')[:TOKEN_SECRET_LEN]