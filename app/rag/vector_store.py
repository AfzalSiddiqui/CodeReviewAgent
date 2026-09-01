import chromadb


class VectorStore:

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path="./chroma_db"
        )

        self.collection = self.client.get_or_create_collection(
            name="coding_policies"
        )

    def add_policy(
        self,
        policy_id: str,
        text: str,
        metadata: dict | None = None,
    ):
        self.collection.upsert(
            ids=[policy_id],
            documents=[text],
            metadatas=[metadata] if metadata else None,
        )

    def add_policies_bulk(self, policies: list[dict]):
        """Add multiple policies at once.

        Each dict must have 'id' and 'text', with optional 'metadata'.
        """
        if not policies:
            return

        ids = [p["id"] for p in policies]
        documents = [p["text"] for p in policies]
        metadatas = [p.get("metadata", {}) for p in policies]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        n_results: int = 3,
        category_filter: str | None = None,
    ):
        where = {"category": category_filter} if category_filter else None
        return self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

    def count(self) -> int:
        return self.collection.count()

    def reset(self):
        self.client.delete_collection("coding_policies")
        self.collection = self.client.get_or_create_collection(
            name="coding_policies"
        )
