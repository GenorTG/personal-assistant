"""Extract user facts and preferences from messages for vector memory."""
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class UserFactsExtractor:
    """Extract user facts, preferences, and important information from messages."""
    
    # Patterns that indicate user facts/preferences/conversation rules
    FACT_PATTERNS = [
        # Personal information
        r'\b(?:my|i am|i\'m|i have|my name is|i\'m called|call me)\s+([^.!?]+)',
        r'\b(?:i (?:am|was|will be|turn|turned))\s+(\d+)\s*(?:years? old|yo)',
        r'\b(?:i (?:live|work|study) (?:in|at|near))\s+([^.!?]+)',
        r'\b(?:my (?:surname|last name|family name|age|birthday|birth date|email|phone|address|job|occupation|profession|hobby|hobbies|favorite|favourite|preference|preferences))\s+(?:is|are|:)\s*([^.!?]+)',
        
        # Preferences
        r'\b(?:i (?:like|love|hate|prefer|dislike|enjoy|don\'t like))\s+([^.!?]+)',
        r'\b(?:my (?:favorite|favourite|preferred|preference))\s+([^.!?]+)',
        r'\b(?:i (?:usually|always|never|often|sometimes))\s+([^.!?]+)',
        
        # Facts about user
        r'\b(?:i (?:have|own|drive|use))\s+([^.!?]+)',
        r'\b(?:my (?:pet|dog|cat|car|computer|laptop|phone))\s+([^.!?]+)',
        
        # Important events/context
        r'\b(?:i (?:just|recently|yesterday|today|last week|this week))\s+([^.!?]+)',
        r'\b(?:remember|note|important|keep in mind)\s+([^.!?]+)',
        
        # Conversation rules and preferences
        r'\b(?:i (?:prefer|like|want|don\'t want|hate|dislike))\s+(?:you|assistant|ai|when you|that you)\s+([^.!?]+)',
        r'\b(?:please (?:don\'t|do|always|never))\s+([^.!?]+)',
        r'\b(?:you (?:should|shouldn\'t|can|can\'t|must|mustn\'t))\s+([^.!?]+)',
        r'\b(?:i (?:don\'t|do not) (?:like|want|appreciate))\s+(?:when|if)\s+([^.!?]+)',
        r'\b(?:when (?:i|we|you))\s+([^.!?]+)',
        r'\b(?:our (?:conversation|chat|interaction|relationship))\s+([^.!?]+)',
    ]
    
    # Patterns that indicate NOT worth saving (trivial conversation)
    NOISE_PATTERNS = [
        r'^(?:hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure|alright|bye|goodbye)\.?$',
        r'^(?:how are you|what\'s up|how\'s it going)\??$',
        r'^(?:can you|could you|please|would you)\s+(?:help|do|tell|show|explain)\??$',
        r'^(?:what|when|where|why|how|who)\s+(?:is|are|was|were|do|does|did)\s+\w+\??$',
    ]
    
    @staticmethod
    def should_save_message(message: str, role: str) -> bool:
        """Determine if a message should be saved to vector memory.
        
        Only saves messages that contain user facts, preferences, or important information.
        Skips random conversation, greetings, questions, etc.
        
        Args:
            message: Message content
            role: Message role (user/assistant/system)
            
        Returns:
            True if message should be saved, False otherwise
        """
        if not message or not message.strip():
            return False
        
        # Only save user messages (assistant messages are responses, not facts)
        if role != "user":
            return False
        
        message_lower = message.lower().strip()
        
        # Skip if it's clearly noise (greetings, simple questions, etc.)
        for pattern in UserFactsExtractor.NOISE_PATTERNS:
            if re.match(pattern, message_lower, re.IGNORECASE):
                return False
        
        # Check if message contains user facts/preferences
        for pattern in UserFactsExtractor.FACT_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.debug(f"Message matches fact pattern: {message[:100]}...")
                return True
        
        # Also check for explicit fact statements (user telling assistant about themselves)
        fact_indicators = [
            'my name', 'i am', "i'm", 'my age', 'my surname', 'my last name',
            'i like', 'i love', 'i prefer', 'my favorite', 'my favourite',
            'i have', 'i own', 'i live', 'i work', 'i study',
            'remember that', 'keep in mind', 'note that',
            'my hobby', 'my hobbies', 'my job', 'my profession',
            # Conversation rules and preferences
            'i prefer you', 'i like when you', 'i want you to', "i don't want you",
            'you should', "you shouldn't", 'you can', "you can't",
            'please don\'t', 'please do', 'when i', 'when we', 'when you',
            'our conversation', 'our chat', 'our interaction',
            'i don\'t like when', 'i hate when', 'i appreciate when',
        ]
        
        for indicator in fact_indicators:
            if indicator in message_lower:
                logger.debug(f"Message contains fact indicator '{indicator}': {message[:100]}...")
                return True
        
        # Check for conversation context and rules (longer messages that establish patterns)
        # If message is substantial and contains context about the relationship/interaction
        if len(message.strip()) >= 30:
            # Check if it contains context about their interaction
            context_indicators = [
                'usually', 'always', 'never', 'often', 'sometimes',
                'when i ask', 'when you respond', 'in our conversations',
                'i noticed', 'i realized', 'i think', 'i feel',
                'we usually', 'we always', 'we never',
            ]
            
            for indicator in context_indicators:
                if indicator in message_lower:
                    logger.debug(f"Message contains context indicator '{indicator}': {message[:100]}...")
                    return True
        
        # Skip if message is very short (likely just a greeting or simple response)
        if len(message.strip()) < 15:
            return False
        
        # Skip if it's just a simple question without context
        if message.strip().endswith('?') and len(message.split()) < 8:
            return False
        
        # For longer messages (30+ words), save them as they likely contain context
        # about the conversation or relationship
        if len(message.split()) >= 30:
            logger.debug(f"Saving longer message as it likely contains context: {message[:100]}...")
            return True
        
        # Default: don't save very short random conversation
        return False
    
    @staticmethod
    def extract_user_facts(messages: List[Dict[str, Any]]) -> List[str]:
        """Extract user facts from a list of messages.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            List of extracted fact strings
        """
        facts = []
        for message in messages:
            content = message.get("content", "")
            role = message.get("role", "")
            
            if UserFactsExtractor.should_save_message(content, role):
                facts.append(content)
        
        return facts
