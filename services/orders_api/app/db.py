from pymongo import MongoClient
from pymongo.collection import Collection


def orders_collection(uri: str) -> Collection:
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return client.get_default_database()["orders"]
