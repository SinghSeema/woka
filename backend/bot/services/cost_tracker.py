"""Cost tracking and estimation for API usage."""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Pricing per 1M tokens (as of 2024, adjust as needed)
PRICING = {
    "llama-3.3-70b-versatile": {
        "input": 0.59,  # $0.59 per 1M input tokens
        "output": 0.79,  # $0.79 per 1M output tokens
    },
    "llama-3.1-8b-instant": {
        "input": 0.05,
        "output": 0.08,
    },
    "text-embedding-3-small": {
        "input": 0.02,  # $0.02 per 1M tokens
    },
    "text-embedding-3-large": {
        "input": 0.13,
    },
    "default": {
        "input": 0.50,
        "output": 0.50,
    }
}


def calculate_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int = 0
) -> float:
    """Calculate cost for LLM API call.
    
    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Cost in USD
    """
    pricing = PRICING.get(model, PRICING["default"])
    
    input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0.50)
    output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0.50)
    
    return input_cost + output_cost


def calculate_embedding_cost(
    model: str,
    tokens: int
) -> float:
    """Calculate cost for embedding generation.
    
    Args:
        model: Embedding model name
        tokens: Number of tokens
        
    Returns:
        Cost in USD
    """
    pricing = PRICING.get(model, PRICING.get("text-embedding-3-small", PRICING["default"]))
    
    cost = (tokens / 1_000_000) * pricing.get("input", 0.02)
    return cost


def estimate_session_cost(
    total_input_tokens: int,
    total_output_tokens: int,
    embedding_tokens: int = 0,
    llm_model: str = None,
    embedding_model: str = None
) -> Dict[str, Any]:
    """Estimate total cost for a session.
    
    Args:
        total_input_tokens: Total LLM input tokens
        total_output_tokens: Total LLM output tokens
        embedding_tokens: Total embedding tokens
        llm_model: LLM model name (defaults to settings)
        embedding_model: Embedding model name (defaults to settings)
        
    Returns:
        Dictionary with cost breakdown
    """
    if llm_model is None:
        llm_model = settings.LLM_MODEL
    if embedding_model is None:
        embedding_model = settings.EMBEDDING_MODEL
    
    llm_cost = calculate_llm_cost(llm_model, total_input_tokens, total_output_tokens)
    embedding_cost = calculate_embedding_cost(embedding_model, embedding_tokens) if embedding_tokens > 0 else 0.0
    
    total_cost = llm_cost + embedding_cost
    
    return {
        "llm_cost": llm_cost,
        "embedding_cost": embedding_cost,
        "total_cost": total_cost,
        "llm_input_tokens": total_input_tokens,
        "llm_output_tokens": total_output_tokens,
        "embedding_tokens": embedding_tokens,
        "total_tokens": total_input_tokens + total_output_tokens + embedding_tokens
    }


def log_cost_summary(
    user_name: str,
    room_name: str,
    cost_breakdown: Dict[str, Any]
) -> None:
    """Log cost summary for a session.
    
    Args:
        user_name: User's name
        room_name: Room/session identifier
        cost_breakdown: Cost breakdown dictionary from estimate_session_cost
    """
    if not getattr(settings, 'TRACK_COSTS', True):
        return
    
    logger.info("=" * 60)
    logger.info("💰 SESSION TOKEN & COST SUMMARY")
    logger.info(f"   User: {user_name}")
    logger.info(f"   Room: {room_name}")
    
    # Always show token counts (even for free models)
    total_tokens = cost_breakdown.get('total_tokens', 0)
    input_tokens = cost_breakdown.get('llm_input_tokens', 0)
    output_tokens = cost_breakdown.get('llm_output_tokens', 0)
    
    logger.info(f"   📊 Token Usage:")
    logger.info(f"      Input Tokens: {input_tokens:,}")
    logger.info(f"      Output Tokens: {output_tokens:,}")
    logger.info(f"      Total Tokens: {total_tokens:,}")
    
    # Show costs (may be $0 for free models)
    total_cost = cost_breakdown.get('total_cost', 0.0)
    if total_cost > 0:
        logger.info(f"   💵 Cost Breakdown:")
        logger.info(f"      LLM Cost: ${cost_breakdown.get('llm_cost', 0):.6f}")
        if cost_breakdown.get('embedding_cost', 0) > 0:
            logger.info(f"      Embedding Cost: ${cost_breakdown['embedding_cost']:.6f}")
        logger.info(f"      Total Cost: ${total_cost:.6f}")
        if total_tokens > 0:
            cost_per_1k = (total_cost / total_tokens * 1000)
            logger.info(f"      Cost per 1K tokens: ${cost_per_1k:.6f}")
    else:
        logger.info(f"   💵 Cost: $0.000000 (Free model)")
    
    logger.info("=" * 60)

