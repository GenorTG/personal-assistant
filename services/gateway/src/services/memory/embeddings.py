"""Embedding model wrapper."""
from typing import List, Union
from sentence_transformers import SentenceTransformer
from ...config.settings import settings
import numpy as np
import asyncio


class EmbeddingModel:
    """Wrapper for sentence-transformers embedding model.
    
    This class handles embedding generation using sentence-transformers.
    Models are automatically downloaded from HuggingFace on first use.
    """
    
    def __init__(self):
        self.model_name = settings.embedding_model
        self.model: Union[SentenceTransformer, None] = None
        self._initialized = False
    
    def _initialize_model(self):
        """Initialize embedding model (auto-downloads on first use).
        
        SentenceTransformer automatically downloads models from HuggingFace
        on first use. The model is cached locally for subsequent uses.
        """
        if not self._initialized:
            try:
                # SentenceTransformer auto-downloads models from HuggingFace
                # This may take time on first use
                print(f"Initializing embedding model: {self.model_name}")
                print("Note: Model will be auto-downloaded from HuggingFace on first use")
                self.model = SentenceTransformer(self.model_name)
                self._initialized = True
                print(f"Embedding model '{self.model_name}' initialized successfully")
            except Exception as e:
                print(f"Error initializing embedding model: {e}")
                raise
    
    async def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """Generate embedding for text.
        
        Args:
            text: Single text string or list of text strings
        
        Returns:
            Numpy array of embeddings (1D for single text, 2D for list)
        
        Raises:
            RuntimeError: If model initialization fails
        """
        if not self.model:
            # Run model initialization in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._initialize_model)
        
        if not self.model:
            raise RuntimeError("Failed to initialize embedding model")
        
        # Run encoding in thread pool (sentence-transformers is CPU-bound)
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False
            )
        )
        
        return embedding
    
    def encode_sync(self, text: Union[str, List[str]]) -> np.ndarray:
        """Synchronous version of encode (for use in non-async contexts).
        
        Args:
            text: Single text string or list of text strings
        
        Returns:
            Numpy array of embeddings
        """
        if not self.model:
            self._initialize_model()
        
        if not self.model:
            raise RuntimeError("Failed to initialize embedding model")
        
        return self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model.
        
        Returns:
            Embedding dimension (e.g., 384 for all-MiniLM-L6-v2)
        """
        if not self.model:
            self._initialize_model()
        
        if not self.model:
            raise RuntimeError("Failed to initialize embedding model")
        
        # Get dimension from model
        return self.model.get_sentence_embedding_dimension()
