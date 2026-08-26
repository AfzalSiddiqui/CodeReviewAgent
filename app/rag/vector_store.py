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
        text: str
    ):
        self.collection.add(
            ids=[policy_id],
            documents=[text]
        )

    def search(
        self,
        query: str,
        n_results: int = 3
    ):
        return self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
