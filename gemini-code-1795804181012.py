import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).with_name(".env"))

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("Falta GEMINI_API_KEY en el entorno o en el archivo .env.")

with genai.Client(api_key=api_key) as client:
    for model in client.models.list():
        print(model.name)