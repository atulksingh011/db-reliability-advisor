import json
import os
from typing import Annotated

import httpx
import typer

app = typer.Typer(help="Run mock/illustrative scenarios through the Analysis Service.")


@app.command()
def run(
    scenario: Annotated[str, typer.Argument(help="query-regression or connection-pressure")],
    base_url: Annotated[
        str,
        typer.Option(help="Analysis Service base URL"),
    ] = os.getenv("ANALYSIS_SERVICE_URL", "http://localhost:8000"),
) -> None:
    if scenario not in {"query-regression", "connection-pressure"}:
        raise typer.BadParameter("scenario must be query-regression or connection-pressure")
    response = httpx.post(f"{base_url}/api/v1/dev/mock/{scenario}", timeout=30)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    app()
