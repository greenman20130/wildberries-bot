import os
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv('BOT_TOKEN')
database_url = os.getenv('DATABASE_URL')
jwt_token = os.getenv('JWT_TOKEN')