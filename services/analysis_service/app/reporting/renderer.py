from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
