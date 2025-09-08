import pytest
from unittest.mock import patch, MagicMock

from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.embeddings.fastembed import FastEmbedProvider
from mcp_server_qdrant.embeddings.voyageai import VoyageAIProvider
from mcp_server_qdrant.embeddings.types import EmbeddingProviderType
from mcp_server_qdrant.settings import EmbeddingProviderSettings


class TestEmbeddingFactory:
    """Test the embedding provider factory functionality."""

    def test_create_fastembed_provider_default(self):
        """Test creating FastEmbed provider with default settings."""
        settings = EmbeddingProviderSettings()
        provider = create_embedding_provider(settings)

        assert isinstance(provider, FastEmbedProvider)
        assert provider.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert settings.provider_type == EmbeddingProviderType.FASTEMBED

    def test_create_voyageai_provider(self):
        """Test creating VoyageAI provider."""
        settings = EmbeddingProviderSettings(
            provider='voyageai',
            model='voyage-3.5'
        )
        provider = create_embedding_provider(settings)

        assert isinstance(provider, VoyageAIProvider)
        assert provider.model_name == "voyage-3.5"
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI

    def test_create_voyageai_provider_different_models(self):
        """Test creating VoyageAI provider with different specialized models."""
        test_cases = [
            'voyage-code-3',
            'voyage-law-2',
            'voyage-finance-2',
            'voyage-3.5-lite',
        ]

        for model in test_cases:
            settings = EmbeddingProviderSettings(
                provider='voyageai',
                model=model
            )
            provider = create_embedding_provider(settings)

            assert isinstance(provider, VoyageAIProvider)
            assert provider.model_name == model
            assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI

    def test_unsupported_provider_type_error(self):
        """Test that unsupported provider types raise appropriate error."""
        settings = EmbeddingProviderSettings()

        # Manually set an invalid provider type to test factory error handling
        with patch.object(settings, 'provider_type', 'invalid_provider'):
            with pytest.raises(ValueError, match="Unsupported embedding provider: invalid_provider"):
                create_embedding_provider(settings)

    def test_provider_interface_compliance(self):
        """Test that all created providers implement the required interface."""
        providers_to_test = [
            EmbeddingProviderSettings(provider='fastembed', model='sentence-transformers/all-MiniLM-L6-v2'),
            EmbeddingProviderSettings(provider='voyageai', model='voyage-3.5'),
        ]

        required_methods = [
            'embed_documents',
            'embed_query',
            'get_vector_name',
            'get_vector_size'
        ]

        for settings in providers_to_test:
            provider = create_embedding_provider(settings)

            # Check that all required methods exist and are callable
            for method_name in required_methods:
                assert hasattr(provider, method_name), f"Provider missing method: {method_name}"
                method = getattr(provider, method_name)
                assert callable(method), f"Provider method {method_name} is not callable"

    def test_vector_specifications_are_different(self):
        """Test that different provider types produce different vector specifications."""
        fastembed_settings = EmbeddingProviderSettings(
            provider='fastembed',
            model='sentence-transformers/all-MiniLM-L6-v2'
        )
        voyageai_settings = EmbeddingProviderSettings(
            provider='voyageai',
            model='voyage-3.5'
        )

        fastembed_provider = create_embedding_provider(fastembed_settings)
        voyageai_provider = create_embedding_provider(voyageai_settings)

        # Vector names should be different to avoid conflicts
        fastembed_vector_name = fastembed_provider.get_vector_name()
        voyageai_vector_name = voyageai_provider.get_vector_name()

        assert fastembed_vector_name != voyageai_vector_name
        assert fastembed_vector_name.startswith('fast-')
        assert voyageai_vector_name.startswith('voyage-')

        # Vector sizes should be valid
        fastembed_size = fastembed_provider.get_vector_size()
        voyageai_size = voyageai_provider.get_vector_size()

        assert isinstance(fastembed_size, int)
        assert isinstance(voyageai_size, int)
        assert fastembed_size > 0
        assert voyageai_size > 0

    def test_factory_preserves_model_names(self):
        """Test that the factory preserves model names correctly."""
        test_cases = [
            ('fastembed', 'sentence-transformers/all-MiniLM-L6-v2'),
            ('voyageai', 'voyage-3.5'),
            ('voyageai', 'voyage-code-3'),
            ('voyageai', 'voyage-law-2'),
        ]

        for provider_type, model_name in test_cases:
            settings = EmbeddingProviderSettings(provider=provider_type, model=model_name)
            provider = create_embedding_provider(settings)
            assert provider.model_name == model_name

    def test_environment_variable_integration(self, monkeypatch):
        """Test that factory works with environment variable configuration."""
        # Test FastEmbed via environment (default)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "fastembed")
        monkeypatch.setenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

        fastembed_settings = EmbeddingProviderSettings()
        fastembed_provider = create_embedding_provider(fastembed_settings)

        assert isinstance(fastembed_provider, FastEmbedProvider)
        assert fastembed_provider.model_name == "sentence-transformers/all-MiniLM-L6-v2"

        # Test VoyageAI via environment
        monkeypatch.setenv("EMBEDDING_PROVIDER", "voyageai")
        monkeypatch.setenv("EMBEDDING_MODEL", "voyage-law-2")

        voyageai_settings = EmbeddingProviderSettings()
        voyageai_provider = create_embedding_provider(voyageai_settings)

        assert isinstance(voyageai_provider, VoyageAIProvider)
        assert voyageai_provider.model_name == "voyage-law-2"

    def test_provider_validation_fallback(self):
        """Test that invalid provider types fall back to FastEmbed."""
        # Test with invalid provider string
        settings = EmbeddingProviderSettings(
            provider='invalid_provider',
            model='sentence-transformers/all-MiniLM-L6-v2'
        )

        # Should fall back to FastEmbed due to validation
        provider = create_embedding_provider(settings)
        assert isinstance(provider, FastEmbedProvider)
        assert settings.provider_type == EmbeddingProviderType.FASTEMBED

    def test_case_insensitive_provider_validation(self):
        """Test that provider validation is case insensitive."""
        test_cases = [
            'voyageai',
            'VOYAGEAI',
            'VoyageAI',
        ]

        for provider_string in test_cases:
            settings = EmbeddingProviderSettings(
                provider=provider_string,
                model='voyage-3.5'
            )
            provider = create_embedding_provider(settings)
            assert isinstance(provider, VoyageAIProvider)
            assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
