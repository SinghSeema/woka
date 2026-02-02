"""System prompt building service for the bot."""

import sys
from pathlib import Path
from typing import Optional

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.logging import get_logger
from bot.services.context_manager import estimate_tokens

logger = get_logger(__name__)


def build_base_system_prompt(user_name: str, bot_name: Optional[str] = None) -> str:
    """Build the base system prompt for the bot.
    
    This creates the core system prompt without past context, which is added
    dynamically via Shadow Memory or PastContextProcessor.
    
    Args:
        user_name: Name of the user for personalization
        bot_name: Name of the bot (defaults to settings.BOT_NAME)
        
    Returns:
        Base system prompt string
    """
    if bot_name is None:
        bot_name = settings.BOT_NAME
    
    prompt = f"""
## ROLE
You are "{bot_name}," an empathetic, professional, and motivational Wellness Coach. Your goal is to help {user_name} achieve their health goals through lifestyle, habit formation, and positive mindset shifts.

## CORE PRINCIPLES
1. **Scope of Practice:** You provide advice on nutrition, exercise, sleep, and stress management. 
2. **Safety First:** You are NOT a doctor, therapist, or medical professional. 
3. **Guardrails:** If {user_name} asks for medical diagnoses, prescriptions, or advice on chronic illnesses/injuries, you must refuse and redirect to a professional.
4. **Ethics:** Never encourage extreme diets, self-harm, or dangerous physical activities. If a request is "wrong" or potentially harmful, politely decline.

## BOUNDARIES & DISCLAIMERS
- **Mandatory Disclaimer:** If a user asks about a health condition, start with: "I'm here to support your wellness journey, but I'm not a medical professional. Please consult a doctor for medical concerns."
- **Refusal Protocol:** If the user asks something outside your scope or unethical, say: "I'm focused on wellness coaching (habits, movement, and mindset). I cannot provide advice on [Topic], as that falls outside my expertise."

## STYLE & TONE
- **Tone:** Grounded, encouraging, and clear. 
- **Style:** Keep responses concise (ideal for voice interaction). Avoid long lists.
- **Greeting:** Start by warmly greeting {user_name} and acknowledging their progress.

## INITIAL TASK
Greet {user_name} and ask how their energy levels are today.
"""
    
    # Validate prompt size
    prompt_size = len(prompt)
    estimated_tokens = estimate_tokens(prompt)
    
    if prompt_size > settings.SYSTEM_PROMPT_MAX_SIZE:
        logger.warning(
            f"⚠️  Base system prompt exceeds recommended size: {prompt_size} chars "
            f"({estimated_tokens} tokens) > {settings.SYSTEM_PROMPT_MAX_SIZE} chars"
        )
    
    if prompt_size > settings.SYSTEM_PROMPT_ERROR_SIZE:
        logger.error(
            f"❌ Base system prompt exceeds error threshold: {prompt_size} chars "
            f"({estimated_tokens} tokens) > {settings.SYSTEM_PROMPT_ERROR_SIZE} chars"
        )
    
    logger.debug(
        f"📋 Built base system prompt: {prompt_size} chars ({estimated_tokens} tokens)"
    )
    
    return prompt.strip()


def build_system_prompt_with_past_context(
    user_name: str,
    past_context: str = "",
    bot_name: Optional[str] = None
) -> str:
    """Build complete system prompt with optional past context.
    
    Args:
        user_name: Name of the user for personalization
        past_context: Optional past session context to append
        bot_name: Name of the bot (defaults to settings.BOT_NAME)
        
    Returns:
        Complete system prompt string
    """
    base_prompt = build_base_system_prompt(user_name, bot_name)
    
    if not past_context:
        return base_prompt
    
    # Append past context if provided
    complete_prompt = base_prompt + "\n\n" + past_context
    
    # Validate complete prompt size
    complete_size = len(complete_prompt)
    estimated_tokens = estimate_tokens(complete_prompt)
    
    if complete_size > settings.SYSTEM_PROMPT_MAX_SIZE:
        logger.warning(
            f"⚠️  Complete system prompt exceeds recommended size: {complete_size} chars "
            f"({estimated_tokens} tokens)"
        )
    
    logger.debug(
        f"📋 Built complete system prompt: {complete_size} chars ({estimated_tokens} tokens)"
    )
    
    return complete_prompt.strip()

