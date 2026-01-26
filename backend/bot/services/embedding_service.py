"""Embedding generation service for semantic search."""

import sys
from pathlib import Path
from typing import List, Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache for embedding model (if using local model)
_embedding_model = None


async def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate vector embedding for text.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        List of floats representing the embedding vector, or None if generation fails
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding generation")
        return None
    
    if not settings.ENABLE_SEMANTIC_SEARCH:
        logger.debug("Semantic search disabled, skipping embedding generation")
        return None
    
    try:
        # Use OpenAI embeddings API
        if settings.EMBEDDING_MODEL.startswith("text-embedding"):
            logger.debug("Attempting OpenAI embedding generation")
            embedding = await _generate_openai_embedding(text)
            if embedding:
                return embedding
            # If OpenAI failed, fall through to local model
            logger.info("OpenAI embedding failed, falling back to local model")
        
        # Use local model (either as primary or fallback)
        logger.debug("Using local embedding model")
        return await _generate_local_embedding(text)
    except Exception as e:
        logger.error(f"❌ Error generating embedding: {e}", exc_info=True)
        return None


async def _generate_openai_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding using OpenAI API.
    
    Args:
        text: Text to embed
        
    Returns:
        Embedding vector or None
    """
    try:
        import httpx
        
        # Check if OpenAI API key is available
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not openai_api_key:
            logger.warning("OpenAI API key not found, falling back to local embeddings")
            return await _generate_local_embedding(text)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.EMBEDDING_MODEL,
                    "input": text,
                },
            )
            response.raise_for_status()
            result = response.json()
            embedding = result["data"][0]["embedding"]
            logger.debug(f"Generated OpenAI embedding: {len(embedding)} dimensions")
            return embedding
            
    except ImportError:
        logger.warning("httpx not available, falling back to local embeddings")
        return await _generate_local_embedding(text)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limit error - log and fallback to local
            logger.warning(
                f"OpenAI API rate limited (429). Falling back to local embeddings. "
                f"Consider adding retry logic or upgrading OpenAI plan."
            )
            return await _generate_local_embedding(text)
        else:
            logger.error(f"OpenAI API error ({e.response.status_code}): {e}", exc_info=True)
            return await _generate_local_embedding(text)
    except Exception as e:
        logger.error(f"Error calling OpenAI embedding API: {e}", exc_info=True)
        # Fallback to local embeddings
        return await _generate_local_embedding(text)


async def _generate_local_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding using local sentence-transformers model.
    
    Args:
        text: Text to embed
        
    Returns:
        Embedding vector or None
    """
    global _embedding_model
    
    try:
        from sentence_transformers import SentenceTransformer
        
        # Load model if not already loaded
        if _embedding_model is None:
            model_name = getattr(settings, 'LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            logger.info(f"🔄 Loading local embedding model: {model_name} (this may take a moment on first load)")
            try:
                _embedding_model = SentenceTransformer(model_name)
                logger.info(f"✅ Local embedding model loaded successfully: {model_name}")
            except Exception as load_error:
                logger.error(f"❌ Failed to load embedding model {model_name}: {load_error}", exc_info=True)
                return None
        
        if _embedding_model is None:
            logger.error("Embedding model is None after loading attempt")
            return None
        
        # Generate embedding (run in thread pool to avoid blocking)
        import asyncio
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: _embedding_model.encode(text, convert_to_numpy=True).tolist()
        )
        logger.info(f"✅ Generated local embedding: {len(embedding)} dimensions")
        return embedding
        
    except ImportError:
        logger.error(
            "❌ sentence-transformers not installed. Install with: pip install sentence-transformers"
        )
        return None
    except Exception as e:
        logger.error(f"❌ Error generating local embedding: {e}", exc_info=True)
        return None


def get_embedding_dimension() -> int:
    """Get the dimension of embeddings based on model.
    
    Returns:
        Embedding dimension
    """
    if settings.EMBEDDING_MODEL.startswith("text-embedding-3-large"):
        return 3072
    elif settings.EMBEDDING_MODEL.startswith("text-embedding-3-small"):
        return 1536
    elif settings.EMBEDDING_MODEL.startswith("text-embedding-ada-002"):
        return 1536
    else:
        # Default for local models
        return getattr(settings, 'EMBEDDING_DIMENSION', 384)

