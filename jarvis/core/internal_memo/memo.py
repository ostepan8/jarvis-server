from jarvis.core.internal_memo.memo_document import MemoDocument
from typing import Dict, Any, Optional, List


class Memo:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, inital_documents: Optional[List[MemoDocument]] = None):
        """
        Initialize the memo system with optional initial documents.

        :param inital_documents: Optional list of MemoDocument instances to pre-populate the memo.
        """
        self.documents = inital_documents if inital_documents else []

    def add_document(self, document: MemoDocument) -> None:
        """
        Add a new document to the memo.

        :param document: MemoDocument instance to add.
        """
        self.documents.append(document)

    def get_document(self, doc_id: str) -> Optional[MemoDocument]:
        """
        Retrieve a document by its ID.

        :param doc_id: Unique identifier of the document.
        :return: MemoDocument instance if found, otherwise None.
        """
        for doc in self.documents:
            if doc.id == doc_id:
                return doc
        return None

    def remove_document(self, doc_id: str) -> bool:
        """
        Remove a document by its ID.

        :param doc_id: Unique identifier of the document.
        :return: True if the document was removed, otherwise False.
        """
        for i, doc in enumerate(self.documents):
            if doc.id == doc_id:
                del self.documents[i]
                return True
        return False

    def update_document(self, doc_id: str, updated_doc: MemoDocument) -> bool:
        """
        Update an existing document by its ID.

        :param doc_id: Unique identifier of the document to update.
        :param updated_doc: MemoDocument instance with updated content.
        :return: True if the document was updated, otherwise False.
        """
        for i, doc in enumerate(self.documents):
            if doc.id == doc_id:
                self.documents[i] = updated_doc
                return True
        return False

    def get_documents(self) -> List[MemoDocument]:
        """
        Retrieve all documents in the memo.

        :return: List of MemoDocument instances.
        """
        return self.documents

    def __repr__(self):
        return f"Memo(documents={self.documents})"
