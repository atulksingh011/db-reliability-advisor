import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import typer
from pymongo import ASCENDING, DESCENDING, MongoClient

app = typer.Typer(help="Seed deterministic demo orders for later real-adapter work.")


@app.command()
def seed(
    count: int = typer.Option(int(os.getenv("MONGO_SEED_RECORDS", "200000")), min=1),
    uri: str = typer.Option(os.getenv("MONGODB_URI", "mongodb://localhost:27017/reliability_demo")),
    batch_size: int = typer.Option(5000, min=1),
) -> None:
    collection = MongoClient(uri).get_default_database()["orders"]
    collection.create_index(
        [("customerId", ASCENDING), ("status", ASCENDING), ("createdAt", DESCENDING)],
        name="customer_status_created_at",
    )
    statuses = ["pending", "paid", "shipped", "cancelled"]
    regions = ["ap-south", "eu-west", "us-east", "us-west"]
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    for offset in range(0, count, batch_size):
        documents = []
        for index in range(offset, min(offset + batch_size, count)):
            documents.append(
                {
                    "orderId": f"ORD-{index:08d}",
                    "customerId": f"CUST-{index % 10000:05d}",
                    "status": statuses[index % len(statuses)],
                    "createdAt": base_time + timedelta(minutes=index),
                    "totalAmount": float(Decimal(1000 + (index % 50000)) / Decimal("100")),
                    "region": regions[index % len(regions)],
                }
            )
        collection.insert_many(documents, ordered=False)
        typer.echo(f"Inserted {min(offset + batch_size, count)}/{count}")

    typer.echo("Deterministic seed complete")


if __name__ == "__main__":
    app()
