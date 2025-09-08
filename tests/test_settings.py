import pytest

from mcp_server_qdrant.embeddings.types import EmbeddingProviderType
from mcp_server_qdrant.settings import (
    DEFAULT_TOOL_FIND_DESCRIPTION,
    DEFAULT_TOOL_STORE_DESCRIPTION,
    EmbeddingProviderSettings,
    QdrantSettings,
    ToolSettings,
)


class TestQdrantSettings:
    def test_default_values(self):
        """Test that required fields raise errors when not provided."""

        # Should not raise error because there are no required fields
        QdrantSettings()

    def test_minimal_config(self, monkeypatch):
        """Test loading minimal configuration from environment variables."""
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("COLLECTION_NAME", "test_collection")

        settings = QdrantSettings()
        assert settings.location == "http://localhost:6333"
        assert settings.collection_name == "test_collection"
        assert settings.api_key is None
        assert settings.local_path is None

    def test_full_config(self, monkeypatch):
        """Test loading full configuration from environment variables."""
        monkeypatch.setenv("QDRANT_URL", "http://qdrant.example.com:6333")
        monkeypatch.setenv("QDRANT_API_KEY", "test_api_key")
        monkeypatch.setenv("COLLECTION_NAME", "my_memories")
        monkeypatch.setenv("QDRANT_SEARCH_LIMIT", "15")
        monkeypatch.setenv("QDRANT_READ_ONLY", "1")

        settings = QdrantSettings()
        assert settings.location == "http://qdrant.example.com:6333"
        assert settings.api_key == "test_api_key"
        assert settings.collection_name == "my_memories"
        assert settings.search_limit == 15
        assert settings.read_only is True

    def test_local_path_config(self, monkeypatch):
        """Test loading local path configuration from environment variables."""
        monkeypatch.setenv("QDRANT_LOCAL_PATH", "/path/to/local/qdrant")

        settings = QdrantSettings()
        assert settings.local_path == "/path/to/local/qdrant"

    def test_local_path_is_exclusive_with_url(self, monkeypatch):
        """Test that local path cannot be set if Qdrant URL is provided."""
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("QDRANT_LOCAL_PATH", "/path/to/local/qdrant")

        with pytest.raises(ValueError):
            QdrantSettings()

        monkeypatch.delenv("QDRANT_URL", raising=False)
        monkeypatch.setenv("QDRANT_API_KEY", "test_api_key")
        with pytest.raises(ValueError):
            QdrantSettings()


class TestEmbeddingProviderSettings:
    def test_default_values(self):
        """Test default values are set correctly."""
        settings = EmbeddingProviderSettings()
        assert settings.provider_type == EmbeddingProviderType.FASTEMBED
        assert settings.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    def test_custom_values(self, monkeypatch):
        """Test loading custom values from environment variables."""
        monkeypatch.setenv("EMBEDDING_MODEL", "custom_model")
        settings = EmbeddingProviderSettings()
        assert settings.provider_type == EmbeddingProviderType.FASTEMBED
        assert settings.model_name == "custom_model"

    def test_voyageai_provider_string(self):
        """Test that 'voyageai' string is validated to VOYAGE_AI enum."""
        settings = EmbeddingProviderSettings(provider='voyageai', model='voyage-3.5')
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
        assert settings.model_name == 'voyage-3.5'

    def test_voyageai_provider_enum(self):
        """Test that VOYAGE_AI enum is accepted directly."""
        # Note: We can't pass provider_type directly due to field aliases
        # Use the provider field which gets validated to the enum
        settings = EmbeddingProviderSettings(
            provider='voyageai',
            model='voyage-code-3'
        )
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
        assert settings.model_name == 'voyage-code-3'

    def test_voyageai_environment_variables(self, monkeypatch):
        """Test VoyageAI configuration via environment variables."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "voyageai")
        monkeypatch.setenv("EMBEDDING_MODEL", "voyage-law-2")

        settings = EmbeddingProviderSettings()
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
        assert settings.model_name == "voyage-law-2"

    def test_invalid_provider_fallback(self):
        """Test that invalid provider types fall back to FASTEMBED."""
        settings = EmbeddingProviderSettings(provider='invalid_provider', model='some-model')
        assert settings.provider_type == EmbeddingProviderType.FASTEMBED
        # Model should still be preserved
        assert settings.model_name == 'some-model'

    def test_case_insensitive_provider(self):
        """Test that provider validation is case insensitive."""
        settings = EmbeddingProviderSettings(provider='VOYAGEAI', model='voyage-3.5')
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI

    def test_provider_with_whitespace(self):
        """Test that provider validation handles whitespace."""
        settings = EmbeddingProviderSettings(provider='  voyageai  ', model='voyage-3.5')
        assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI

    def test_voyageai_models_variety(self):
        """Test VoyageAI with different model types."""
        test_cases = [
            'voyage-3.5',
            'voyage-code-3',
            'voyage-law-2',
            'voyage-finance-2',
            'voyage-3.5-lite'
        ]

        for model in test_cases:
            settings = EmbeddingProviderSettings(provider='voyageai', model=model)
            assert settings.provider_type == EmbeddingProviderType.VOYAGE_AI
            assert settings.model_name == model


class TestToolSettings:
    def test_default_values(self):
        """Test that default values are set correctly when no env vars are provided."""
        settings = ToolSettings()
        assert settings.tool_store_description == DEFAULT_TOOL_STORE_DESCRIPTION
        assert settings.tool_find_description == DEFAULT_TOOL_FIND_DESCRIPTION

    def test_custom_store_description(self, monkeypatch):
        """Test loading custom store description from environment variable."""
        monkeypatch.setenv("TOOL_STORE_DESCRIPTION", "Custom store description")
        settings = ToolSettings()
        assert settings.tool_store_description == "Custom store description"
        assert settings.tool_find_description == DEFAULT_TOOL_FIND_DESCRIPTION

    def test_custom_find_description(self, monkeypatch):
        """Test loading custom find description from environment variable."""
        monkeypatch.setenv("TOOL_FIND_DESCRIPTION", "Custom find description")
        settings = ToolSettings()
        assert settings.tool_store_description == DEFAULT_TOOL_STORE_DESCRIPTION
        assert settings.tool_find_description == "Custom find description"

    def test_all_custom_values(self, monkeypatch):
        """Test loading all custom values from environment variables."""
        monkeypatch.setenv("TOOL_STORE_DESCRIPTION", "Custom store description")
        monkeypatch.setenv("TOOL_FIND_DESCRIPTION", "Custom find description")
        settings = ToolSettings()
        assert settings.tool_store_description == "Custom store description"
        assert settings.tool_find_description == "Custom find description"
