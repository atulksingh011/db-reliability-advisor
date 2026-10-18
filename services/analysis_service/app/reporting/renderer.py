from hashlib import sha256
from pathlib import Path

from fastapi.templating import Jinja2Templates

from .view_models import report_page_model

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["report_page_model"] = report_page_model

# Content versions prevent a warm browser from mixing new HTML with cached product CSS/JS.
_static = Path(__file__).parent / "static"
TEMPLATES.env.globals["asset_version"] = sha256(
    (_static / "report.css").read_bytes() + (_static / "advisor.js").read_bytes()
).hexdigest()[:12]
