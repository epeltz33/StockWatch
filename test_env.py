import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

print(os.getenv('POLYGON_API_KEY'))
print(os.getenv('APP_NAME'))

