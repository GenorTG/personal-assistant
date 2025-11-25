"""Pydantic schemas for API requests and responses."""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ChatMessage(BaseModel):
    """Chat message schema."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None
    # Metadata for tracking
    metadata: Optional[Dict[str, Any]] = Field(None, description="Message metadata")


class MessageMetadata(BaseModel):
    """Metadata for a chat message (assistant responses)."""
    model_name: Optional[str] = Field(None, description="Model that generated the response")
    generation_time_ms: Optional[float] = Field(None, description="Time taken to generate (ms)")
    tokens_generated: Optional[int] = Field(None, description="Number of tokens generated")
    context_length: Optional[int] = Field(None, description="Context length used")
    # Sampler settings used
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    repeat_penalty: Optional[float] = None
    # Full request context (for debugging)
    full_prompt: Optional[str] = Field(None, description="Full prompt sent to LLM")
    retrieved_context: Optional[List[str]] = Field(None, description="Context retrieved from memory")


class UserProfile(BaseModel):
    """User profile schema."""
    name: str = Field("User", description="User's name")
    about: Optional[str] = Field(None, description="Information about the user")
    preferences: Optional[str] = Field(None, description="User preferences and interests")


class CharacterCard(BaseModel):
    """Character card schema for AI assistant personality."""
    name: str = Field("Assistant", description="Assistant's name")
    personality: str = Field("", description="Personality traits and speaking style")
    background: Optional[str] = Field(None, description="Background information")
    instructions: Optional[str] = Field(None, description="Additional instructions for behavior")


class ChatRequest(BaseModel):
    """Chat request schema."""
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    stream: bool = Field(False, description="Whether to stream the response")
    # User and character settings (optional, will use defaults if not provided)
    character_card: Optional[CharacterCard] = Field(None, description="Character card for this conversation")
    user_profile: Optional[UserProfile] = Field(None, description="User profile for this conversation")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Override temperature setting")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Override top_p setting")
    top_k: Optional[int] = Field(None, ge=0, description="Override top_k setting")
    repeat_penalty: Optional[float] = Field(None, ge=0.0, description="Override repeat_penalty setting")


class ChatResponse(BaseModel):
    """Chat response schema."""
    response: str = Field(..., description="Assistant response")
    conversation_id: str = Field(..., description="Conversation ID")
    context_used: Optional[List[str]] = Field(None, description="Retrieved context from memory")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls made during response")
    metadata: Optional[MessageMetadata] = Field(None, description="Response metadata")


class ConversationHistory(BaseModel):
    """Conversation history schema."""
    conversation_id: str
    messages: List[ChatMessage]
    name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Conversation-level metadata
    total_messages: Optional[int] = None
    model_used: Optional[str] = None


class ConversationRenameRequest(BaseModel):
    """Request to rename a conversation."""
    conversation_id: str = Field(..., description="Conversation ID to rename")
    new_name: str = Field(..., description="New name for the conversation")


class STTRequest(BaseModel):
    """Speech-to-Text request schema."""
    language: Optional[str] = Field(None, description="Language code (e.g., 'en')")


class STTResponse(BaseModel):
    """Speech-to-Text response schema."""
    text: str = Field(..., description="Transcribed text")
    language: Optional[str] = Field(None, description="Detected language")


class TTSRequest(BaseModel):
    """Text-to-Speech request schema."""
    text: str = Field(..., description="Text to synthesize")
    voice: Optional[str] = Field(None, description="Voice identifier")


class ModelLoadOptions(BaseModel):
    """Model loading options schema."""
    n_ctx: Optional[int] = Field(None, ge=512, le=32768, description="Context window size")
    n_threads: Optional[int] = Field(None, ge=1, le=128, description="Number of CPU threads")
    n_gpu_layers: Optional[int] = Field(None, ge=-1, description="Number of GPU layers (-1 = all, 0 = CPU only)")
    use_flash_attention: Optional[bool] = Field(None, description="Enable flash attention (if supported)")
    use_mmap: Optional[bool] = Field(None, description="Use memory mapping")
    use_mlock: Optional[bool] = Field(None, description="Lock memory in RAM")
    # Advanced options
    n_batch: Optional[int] = Field(None, ge=1, le=512, description="Batch size for prompt processing")
    n_predict: Optional[int] = Field(None, ge=-1, description="Maximum tokens to predict (-1 = infinite)")
    rope_freq_base: Optional[float] = Field(None, description="RoPE frequency base")
    rope_freq_scale: Optional[float] = Field(None, description="RoPE frequency scale")
    low_vram: Optional[bool] = Field(None, description="Enable low VRAM mode")
    main_gpu: Optional[int] = Field(None, ge=0, description="Main GPU device ID")
    tensor_split: Optional[List[float]] = Field(None, description="Split model across multiple GPUs")
    n_cpu_moe: Optional[int] = Field(None, description="Number of experts to offload to CPU (for MoE models)")
    cache_type_k: Optional[str] = Field(None, description="KV cache data type for K (f16, q8_0, q4_0)")
    cache_type_v: Optional[str] = Field(None, description="KV cache data type for V (f16, q8_0, q4_0)")
    offload_kqv: Optional[bool] = Field(None, description="Offload KV cache to GPU")


class AISettings(BaseModel):
    """AI settings schema."""
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.9, ge=0.0, le=1.0, description="Top-p sampling")
    top_k: int = Field(40, ge=0, description="Top-k sampling")
    repeat_penalty: float = Field(1.1, ge=0.0, description="Repeat penalty")
    system_prompt: Optional[str] = Field(None, description="System prompt")
    character_card: Optional[CharacterCard] = Field(None, description="Character card for personality")
    user_profile: Optional[UserProfile] = Field(None, description="User profile information")
    default_load_options: Optional[ModelLoadOptions] = Field(None, description="Default model loading options")


class AISettingsResponse(BaseModel):
    """AI settings response schema."""
    model_config = ConfigDict(protected_namespaces=())
    
    settings: AISettings
    model_loaded: bool
    current_model: Optional[str] = None


class ModelInfo(BaseModel):
    """Model information schema."""
    model_config = ConfigDict(protected_namespaces=())
    
    model_id: str
    name: str
    size: Optional[str] = None
    format: str = "gguf"
    downloaded: bool = False


class ModelMetadata(BaseModel):
    """Detailed model metadata schema."""
    name: str
    architecture: str
    parameters: Optional[str] = None  # e.g., "7B", "13B"
    num_parameters: Optional[float] = None  # Actual parameter count
    num_layers: Optional[int] = None
    hidden_size: Optional[int] = None
    quantization: Optional[str] = None
    file_size_gb: Optional[float] = None
    context: Dict[str, int] = Field(default_factory=dict)  # max_length, recommended
    moe: Optional[Dict[str, Any]] = None  # MoE configuration
    config: Optional[Dict[str, Any]] = None  # Raw config


class MemoryEstimate(BaseModel):
    """Memory requirement estimate schema."""
    model_size_gb: float
    kv_cache_gb: float
    activations_gb: float
    overhead_gb: float
    total_gb: float
    recommended_vram_gb: int
    quantization: str
    context_length: int
    batch_size: int
    breakdown: Dict[str, float]
    will_fit: Optional[bool] = None  # Based on available VRAM





class ToolCall(BaseModel):
    """Tool call schema."""
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolResult(BaseModel):
    """Tool result schema."""
    name: str = Field(..., description="Tool name")
    success: bool = Field(..., description="Whether execution succeeded")
    result: Optional[Any] = Field(None, description="Tool result")
    error: Optional[str] = Field(None, description="Error message if failed")


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
