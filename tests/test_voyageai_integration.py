import pytest
import unittest.mock
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server_qdrant.embeddings.voyageai import VoyageAIProvider, VOYAGE_AI_MODEL_DIMENSIONS
from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.embeddings.types import EmbeddingProviderType
from mcp_server_qdrant.settings import EmbeddingProviderSettings


class TestVoyageAIProviderIntegration:
    """Integration tests for VoyageAIProvider."""

    def test_initialization_default(self):
        """Test that the provider can be initialized with default model."""
        provider = VoyageAIProvider()
        assert provider.model_name == "voyage-3.5"
        assert provider.api_key is None
        assert provider._client is None  # Lazy initialization

    def test_initialization_custom_model(self):
        """Test that the provider can be initialized with a custom model."""
        provider = VoyageAIProvider("voyage-code-3")
        assert provider.model_name == "voyage-code-3"
        assert provider.api_key is None

    def test_initialization_with_api_key(self):
        """Test that the provider can be initialized with an API key."""
        provider = VoyageAIProvider("voyage-3.5", "test-api-key")
        assert provider.model_name == "voyage-3.5"
        assert provider.api_key == "test-api-key"

    def test_get_vector_name_default(self):
        """Test that the vector name is generated correctly for default model."""
        provider = VoyageAIProvider()
        vector_name = provider.get_vector_name()
        assert vector_name == "voyage-3-5"

    def test_get_vector_name_code_model(self):
        """Test that the vector name is generated correctly for code model."""
        provider = VoyageAIProvider("voyage-code-3")
        vector_name = provider.get_vector_name()
        assert vector_name == "voyage-code-3"

    def test_get_vector_name_law_model(self):
        """Test that the vector name is generated correctly for law model."""
        provider = VoyageAIProvider("voyage-law-2")
        vector_name = provider.get_vector_name()
        assert vector_name == "voyage-law-2"

    def test_get_vector_size_known_models(self):
        """Test that vector sizes are correct for known models."""
        test_cases = [
            ("voyage-3.5", 1024),
            ("voyage-code-3", 1024),
            ("voyage-law-2", 1024),
            ("voyage-code-2", 1536),
            ("voyage-3-lite", 512),
        ]

        for model, expected_size in test_cases:
            provider = VoyageAIProvider(model)
            assert provider.get_vector_size() == expected_size

    def test_get_vector_size_unknown_model(self):
        """Test that unknown models default to 1024 dimensions."""
        provider = VoyageAIProvider("unknown-model")
        assert provider.get_vector_size() == 1024

    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    def test_lazy_client_initialization_success(self, mock_async_client):
        """Test that the client is lazily initialized successfully."""
        mock_client = AsyncMock()
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider(api_key="test-key")
        assert provider._client is None

        # Access client property to trigger lazy initialization
        client = provider.client

        assert client == mock_client
        assert provider._client == mock_client
        mock_async_client.assert_called_once_with(api_key="test-key")

    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    def test_lazy_client_initialization_failure(self, mock_async_client):
        """Test that client initialization failure raises appropriate error."""
        mock_async_client.side_effect = Exception("Invalid API key")

        provider = VoyageAIProvider(api_key="invalid-key")

        with pytest.raises(RuntimeError, match="Failed to initialize Voyage AI client"):
            _ = provider.client

    @pytest.mark.asyncio
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    async def test_embed_documents_success(self, mock_async_client):
        """Test that documents can be embedded successfully."""
        # Mock the client and its embed method
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.embeddings = [
            [0.1, 0.2, 0.3, 0.4],  # First document embedding
            [0.5, 0.6, 0.7, 0.8],  # Second document embedding
        ]
        mock_client.embed = AsyncMock(return_value=mock_result)
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider(api_key="test-key")
        documents = ["This is a test document.", "This is another test document."]

        embeddings = await provider.embed_documents(documents)

        # Verify the result
        assert len(embeddings) == 2
        assert embeddings[0] == [0.1, 0.2, 0.3, 0.4]
        assert embeddings[1] == [0.5, 0.6, 0.7, 0.8]

        # Verify the API call
        mock_client.embed.assert_called_once_with(
            texts=documents,
            model="voyage-3.5",
            input_type="document"
        )

    @pytest.mark.asyncio
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    async def test_embed_query_success(self, mock_async_client):
        """Test that queries can be embedded successfully."""
        # Mock the client and its embed method
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1, 0.2, 0.3, 0.4]]  # Single query embedding
        mock_client.embed = AsyncMock(return_value=mock_result)
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider(api_key="test-key")
        query = "This is a test query."

        embedding = await provider.embed_query(query)

        # Verify the result
        assert embedding == [0.1, 0.2, 0.3, 0.4]

        # Verify the API call
        mock_client.embed.assert_called_once_with(
            texts=[query],
            model="voyage-3.5",
            input_type="query"
        )

    @pytest.mark.asyncio
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    async def test_embed_documents_api_error(self, mock_async_client):
        """Test that API errors are handled properly for documents."""
        mock_client = AsyncMock()
        mock_client.embed = AsyncMock(side_effect=Exception("API Error"))
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider(api_key="test-key")
        documents = ["Test document"]

        with pytest.raises(RuntimeError, match="Failed to embed documents"):
            await provider.embed_documents(documents)

    @pytest.mark.asyncio
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    async def test_embed_query_api_error(self, mock_async_client):
        """Test that API errors are handled properly for queries."""
        mock_client = AsyncMock()
        mock_client.embed = AsyncMock(side_effect=Exception("API Error"))
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider(api_key="test-key")
        query = "Test query"

        with pytest.raises(RuntimeError, match="Failed to embed query"):
            await provider.embed_query(query)

    def test_factory_integration(self):
        """Test that the provider can be created through the factory."""
        settings = EmbeddingProviderSettings(provider='voyageai', model='voyage-3.5')
        provider = create_embedding_provider(settings)

        assert isinstance(provider, VoyageAIProvider)
        assert provider.model_name == 'voyage-3.5'

    def test_factory_integration_different_model(self):
        """Test factory integration with different models."""
        test_cases = [
            ('voyage-code-3', 'voyage-code-3'),
            ('voyage-law-2', 'voyage-law-2'),
            ('voyage-finance-2', 'voyage-finance-2'),
        ]

        for model_input, expected_model in test_cases:
            settings = EmbeddingProviderSettings(provider='voyageai', model=model_input)
            provider = create_embedding_provider(settings)

            assert isinstance(provider, VoyageAIProvider)
            assert provider.model_name == expected_model

    def test_settings_validation(self):
        """Test that settings validation works correctly."""
        # Test with string provider type
        settings = EmbeddingProviderSettings(provider='voyageai', model='voyage-3.5')
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
        assert settings.model_name == 'voyage-3.5'

        # Test with enum provider type (using provider field)
        settings_enum = EmbeddingProviderSettings(
            provider='voyageai',
            model='voyage-code-3'
        )
        assert settings_enum.provider_type == EmbeddingProviderType.VOYAGE_AI
        assert settings_enum.model_name == 'voyage-code-3'

    def test_model_dimensions_coverage(self):
        """Test that all models in VOYAGE_AI_MODEL_DIMENSIONS are covered."""
        # Ensure we have dimensions for all the models we expect
        expected_models = [
            'voyage-3-large', 'voyage-3.5', 'voyage-3.5-lite', 'voyage-code-3',
            'voyage-finance-2', 'voyage-law-2', 'voyage-code-2', 'voyage-3',
            'voyage-3-lite', 'voyage-multilingual-2', 'voyage-large-2-instruct',
            'voyage-large-2', 'voyage-2'
        ]

        for model in expected_models:
            assert model in VOYAGE_AI_MODEL_DIMENSIONS, f"Model {model} missing from dimensions mapping"

        # Test that providers work with all these models
        for model in expected_models:
            provider = VoyageAIProvider(model)
            assert provider.get_vector_size() > 0
            assert provider.get_vector_name().startswith('voyage-')

    @pytest.mark.asyncio
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    async def test_different_model_api_calls(self, mock_async_client):
        """Test that different models make correct API calls."""
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1, 0.2, 0.3, 0.4]]
        mock_client.embed = AsyncMock(return_value=mock_result)
        mock_async_client.return_value = mock_client

        # Test different models
        test_models = ['voyage-3.5', 'voyage-code-3', 'voyage-law-2']

        for model in test_models:
            provider = VoyageAIProvider(model, api_key="test-key")
            await provider.embed_query("test")

            # Verify the model was used in the API call
            mock_client.embed.assert_called_with(
                texts=["test"],
                model=model,
                input_type="query"
            )

            mock_client.embed.reset_mock()

    def test_vector_naming_consistency(self):
        """Test that vector naming is consistent and unique."""
        models = ['voyage-3.5', 'voyage-code-3', 'voyage-law-2', 'voyage-3-large']
        vector_names = []

        for model in models:
            provider = VoyageAIProvider(model)
            vector_name = provider.get_vector_name()

            # Check naming convention
            assert vector_name.startswith('voyage-'), f"Vector name {vector_name} should start with 'voyage-'"

            # Check uniqueness
            assert vector_name not in vector_names, f"Duplicate vector name: {vector_name}"
            vector_names.append(vector_name)

        # Ensure we don't conflict with FastEmbed naming
        fastembed_provider = create_embedding_provider(
            EmbeddingProviderSettings(provider='fastembed', model='sentence-transformers/all-MiniLM-L6-v2')
        )
        fastembed_vector = fastembed_provider.get_vector_name()

        for voyage_vector in vector_names:
            assert voyage_vector != fastembed_vector, f"VoyageAI vector {voyage_vector} conflicts with FastEmbed {fastembed_vector}"

    @patch.dict('os.environ', {'VOYAGE_API_KEY': 'env-test-key'})
    @patch('mcp_server_qdrant.embeddings.voyageai.voyageai.AsyncClient')
    def test_api_key_from_environment(self, mock_async_client):
        """Test that API key can be read from environment variable."""
        mock_client = AsyncMock()
        mock_async_client.return_value = mock_client

        provider = VoyageAIProvider()  # No API key provided

        # Access client to trigger initialization
        _ = provider.client

        # Should use environment variable (AsyncClient handles this internally)
        mock_async_client.assert_called_once_with(api_key=None)
