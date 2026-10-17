from pathlib import Path

from fastapi.templating import Jinja2Templates

from .view_models import report_page_model

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["report_page_model"] = report_page_model
