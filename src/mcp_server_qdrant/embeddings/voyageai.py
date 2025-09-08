import logging
from typing import Dict

import voyageai

from mcp_server_qdrant.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# Voyage AI model specifications - dimension mappings
VOYAGE_AI_MODEL_DIMENSIONS: Dict[str, int] = {
    "voyage-3-large": 1024,
    "voyage-3.5": 1024,
    "voyage-3.5-lite": 1024,
    "voyage-code-3": 1024,
    "voyage-finance-2": 1024,
    "voyage-law-2": 1024,
    "voyage-code-2": 1536,
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-multilingual-2": 1024,
    "voyage-large-2-instruct": 1024,
    "voyage-large-2": 1024,
    "voyage-2": 1024,
}

class VoyageAIProvider(EmbeddingProvider):
    """
    Voyage AI implementation of the embedding provider.
    :param model_name: The name of the Voyage AI model to use.
    :param api_key: Optional API key. If not provided, will use environment variable.
    """

    def __init__(self, model_name: str = "voyage-3.5", api_key: str | None = None):
        self.model_name = model_name
        self.api_key = api_key
        self._client = None

        # Validate model name
        if model_name not in VOYAGE_AI_MODEL_DIMENSIONS:
            logger.warning(f"Model {model_name} not in known models list. Using default dimensions.")

    @property
    def client(self) -> voyageai.AsyncClient:
        """Lazy initialization of the Voyage AI async client."""
        if self._client is None:
            try:
                self._client = voyageai.AsyncClient(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Voyage AI client: {e}")
                raise RuntimeError(
                    "Failed to initialize Voyage AI client. Please ensure VOYAGE_API_KEY is set or provide api_key parameter."
                ) from e
        return self._client

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of documents into vectors."""
        try:
            result = await self.client.embed(
                texts=documents,
                model=self.model_name,
                input_type="document"
            )
            return result.embeddings
        except Exception as e:
            logger.error(f"Error embedding documents with Voyage AI: {e}")
            raise RuntimeError(f"Failed to embed documents: {e}") from e

    async def embed_query(self, query: str) -> list[float]:
        """Embed a query into a vector."""
        try:
            result = await self.client.embed(
                texts=[query],
                model=self.model_name,
                input_type="query"
            )
            return result.embeddings[0]
        except Exception as e:
            logger.error(f"Error embedding query with Voyage AI: {e}")
            raise RuntimeError(f"Failed to embed query: {e}") from e

    def get_vector_name(self) -> str:
        """
        Return the name of the vector for the Qdrant collection.
        Format: voyage-{model-name-simplified}
        """
        # Simplify model name for vector naming
        simplified_name = self.model_name.replace("voyage-", "").replace(".", "-")
        return f"voyage-{simplified_name}"

    def get_vector_size(self) -> int:
        """Get the size of the vector for the Qdrant collection."""
        # Return known dimension or default to 1024 for unknown models
        return VOYAGE_AI_MODEL_DIMENSIONS.get(self.model_name, 1024)
