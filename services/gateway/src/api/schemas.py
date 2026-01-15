"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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
    """Chat request schema with optional sampler settings override.
    
    All sampler parameters are optional - if not provided, saved settings are used.
    """
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    stream: bool = Field(False, description="Whether to stream the response")
    
    # User and character settings (optional, will use defaults if not provided)
    character_card: Optional[CharacterCard] = Field(None, description="Character card for this conversation")
    user_profile: Optional[UserProfile] = Field(None, description="User profile for this conversation")
    
    # Sampler settings (optional - override saved settings for this request)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Top-p sampling")
    top_k: Optional[int] = Field(None, ge=0, description="Top-k sampling")
    min_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum probability threshold")
    repeat_penalty: Optional[float] = Field(None, ge=1.0, le=2.0, description="Repeat penalty")
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Presence penalty")
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Frequency penalty")
    typical_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Typical sampling")
    tfs_z: Optional[float] = Field(None, ge=0.0, description="Tail-free sampling")
    mirostat_mode: Optional[int] = Field(None, ge=0, le=2, description="Mirostat mode")
    mirostat_tau: Optional[float] = Field(None, ge=0.0, le=10.0, description="Mirostat tau")
    mirostat_eta: Optional[float] = Field(None, ge=0.0, le=1.0, description="Mirostat eta")
    max_tokens: Optional[int] = Field(None, ge=-1, le=32768, description="Max tokens to generate")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    seed: Optional[int] = Field(None, description="Random seed (-1=random)")
    grammar: Optional[str] = Field(None, description="GBNF grammar string")
    logit_bias: Optional[Dict[int, float]] = Field(None, description="Token ID bias map")
    penalty_range: Optional[int] = Field(None, ge=0, description="Repetition penalty range")
    penalty_alpha: Optional[float] = Field(None, ge=0.0, description="Contrastive search penalty")
    n_probs: Optional[int] = Field(None, ge=0, description="Return top N probabilities")


class LogEntry(BaseModel):
    """A single log entry from the backend."""
    timestamp: float = Field(..., description="Unix timestamp of the log entry")
    level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    logger: str = Field(..., description="Name of the logger that produced this log")
    message: str = Field(..., description="Log message")
    exception: Optional[str] = Field(None, description="Exception traceback if available")


class BaseResponse(BaseModel):
    """Base response model with optional logs."""
    logs: Optional[List[LogEntry]] = Field(None, description="Request-scoped logs from the backend")


class ChatResponse(BaseModel):
    """Chat response schema."""
    response: str = Field(..., description="Assistant response")
    conversation_id: str = Field(..., description="Conversation ID")
    context_used: Optional[List[str]] = Field(None, description="Retrieved context from memory")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls made during response")
    metadata: Optional[MessageMetadata] = Field(None, description="Response metadata")
    logs: Optional[List[LogEntry]] = Field(None, description="Request-scoped logs from the backend")


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
    pinned: Optional[bool] = False


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


class VoiceModelDownloadRequest(BaseModel):
    """Request to download a voice/STT model asset."""
    model_id: Optional[str] = Field(None, description="Model/voice identifier (backend-specific)")
    url: Optional[str] = Field(None, description="Primary download URL (backend-specific)")
    aux_url: Optional[str] = Field(None, description="Secondary download URL (backend-specific, e.g. config/metadata)")
    force: bool = Field(False, description="Force re-download even if files already exist")


class VoiceModelDownloadStatus(BaseModel):
    """Status response for a model/voice download task."""
    status: str = Field(..., description="queued|downloading|ready|error|not_found")
    model_id: Optional[str] = Field(None, description="Model/voice identifier")
    message: Optional[str] = Field(None, description="Human-friendly status message")
    error: Optional[str] = Field(None, description="Error message if status=error")
    downloaded: bool = Field(False, description="Whether required files are present")
    files: Optional[Dict[str, str]] = Field(None, description="Downloaded file paths (if any)")


class ModelLoadOptions(BaseModel):
    """Model loading options schema for OpenAI-compatible server.
    
    These parameters match the OpenAI-compatible server config format.
    See: https://github.com/abetlen/llama-cpp-python
    """
    # Capability overrides
    supports_tool_calling_override: Optional[bool] = Field(
        None,
        description="Force-enable or disable tool calling flag for this model (overrides auto-detection)"
    )
    # Core parameters
    n_ctx: Optional[int] = Field(None, ge=512, le=131072, description="Context window size")
    n_batch: Optional[int] = Field(None, ge=1, le=4096, description="Batch size for prompt processing")
    n_threads: Optional[int] = Field(None, ge=1, le=128, description="Number of CPU threads")
    n_threads_batch: Optional[int] = Field(None, ge=1, le=128, description="Number of threads for batch processing")
    
    # GPU settings
    n_gpu_layers: Optional[int] = Field(None, ge=-1, description="Number of GPU layers (-1 = all, 0 = CPU only)")
    main_gpu: Optional[int] = Field(None, ge=0, description="Main GPU device ID for multi-GPU")
    tensor_split: Optional[List[float]] = Field(None, description="Split model across multiple GPUs (e.g., [0.5, 0.5])")
    
    # Memory settings
    use_mmap: Optional[bool] = Field(None, description="Use memory mapping for model loading")
    use_mlock: Optional[bool] = Field(None, description="Lock model in RAM to prevent swapping")
    
    # Performance settings
    flash_attn: Optional[bool] = Field(None, description="Enable Flash Attention (requires compatible GPU)")
    
    # RoPE settings (for extended context)
    rope_freq_base: Optional[float] = Field(None, description="RoPE frequency base (for context extension)")
    rope_freq_scale: Optional[float] = Field(None, description="RoPE frequency scale (for context extension)")
    rope_scaling_type: Optional[int] = Field(None, description="RoPE scaling type: -1=unspecified, 0=none, 1=linear, 2=yarn")
    yarn_ext_factor: Optional[float] = Field(None, description="YaRN extrapolation factor (-1.0 = auto)")
    yarn_attn_factor: Optional[float] = Field(None, description="YaRN attention factor")
    yarn_beta_fast: Optional[float] = Field(None, description="YaRN beta fast")
    yarn_beta_slow: Optional[float] = Field(None, description="YaRN beta slow")
    yarn_orig_ctx: Optional[int] = Field(None, description="YaRN original context size")
    
    # KV cache settings
    cache_type_k: Optional[str] = Field(None, pattern="^(f16|f32|q8_0|q4_0|q4_1|iq4_nl|q5_0|q5_1)$", description="KV cache type for K")
    cache_type_v: Optional[str] = Field(None, pattern="^(f16|f32|q8_0|q4_0|q4_1|iq4_nl|q5_0|q5_1)$", description="KV cache type for V")
    
    # MoE (Mixture of Experts) settings
    # Note: n_cpu_moe is not a valid parameter for OpenAI-compatible server
    # It was incorrectly documented as "CPU threads for MoE experts"
    # Deprecated/removed - kept for backwards compatibility, will be ignored
    use_flash_attention: Optional[bool] = Field(None, description="DEPRECATED: Use flash_attn instead")
    offload_kqv: Optional[bool] = Field(None, description="DEPRECATED: Not supported by llama-cpp-python")


class SamplerSettings(BaseModel):
    """Complete sampler settings for OpenAI-compatible server.
    
    These parameters control text generation and match the OpenAI-compatible API.
    """
    # Basic sampling
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature (0=deterministic, 2=very random)")
    top_p: float = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling threshold")
    top_k: int = Field(40, ge=0, description="Top-k sampling (0=disabled)")
    min_p: float = Field(0.0, ge=0.0, le=1.0, description="Minimum probability threshold")
    
    # Repetition control
    repeat_penalty: float = Field(1.1, ge=1.0, le=2.0, description="Repetition penalty (1.0=disabled)")
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="OpenAI-style presence penalty")
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="OpenAI-style frequency penalty")
    repeat_last_n: int = Field(64, ge=-1, description="Tokens to look back for repetition (-1=context)")
    
    # Advanced sampling
    typical_p: float = Field(1.0, ge=0.0, le=1.0, description="Typical sampling (1.0=disabled)")
    tfs_z: float = Field(1.0, ge=0.0, description="Tail-free sampling (1.0=disabled)")
    
    # Mirostat entropy-based sampling
    mirostat_mode: int = Field(0, ge=0, le=2, description="Mirostat mode (0=off, 1=v1, 2=v2)")
    mirostat_tau: float = Field(5.0, ge=0.0, le=10.0, description="Mirostat target entropy")
    mirostat_eta: float = Field(0.1, ge=0.0, le=1.0, description="Mirostat learning rate")
    
    # Output control
    max_tokens: int = Field(512, ge=-1, le=32768, description="Max tokens to generate (-1=unlimited)")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    seed: int = Field(-1, description="Random seed (-1=random)")
    grammar: Optional[str] = Field(None, description="GBNF grammar string for structured output")
    
    # Smooth Sampling - quadratic/cubic probability distribution transformation
    smoothing_factor: Optional[float] = Field(None, ge=0.0, le=1.0, description="Smoothing factor (0.0-1.0). Lower values (0.2-0.3) = more creative. 0.0 = disabled.")
    smoothing_curve: Optional[float] = Field(None, ge=1.0, description="Smoothing curve (1.0+). Higher = steeper curve, punishes low probability choices more. 1.0 = equivalent to only using smoothing_factor.")
    
    # Advanced parameters
    logit_bias: Optional[Dict[int, float]] = Field(None, description="Bias specific token IDs")
    penalty_range: Optional[int] = Field(None, ge=0, description="Range of tokens for repetition penalty")
    penalty_alpha: Optional[float] = Field(None, ge=0.0, description="Contrastive search penalty alpha")
    n_probs: Optional[int] = Field(None, ge=0, description="Return top N token probabilities (debug)")
    
    # DRY (Dynamic Repetition Penalty) - sequence-based repetition control
    # Formula: penalty = multiplier * base^(length - allowed_length)
    dry_multiplier: Optional[float] = Field(None, ge=0.0, description="DRY multiplier: penalty strength (0.0=disabled)")
    dry_base: Optional[float] = Field(None, ge=0.0, description="DRY base: penalty scaling factor for sequence length")
    dry_allowed_length: Optional[int] = Field(None, ge=0, description="DRY allowed length: minimum sequence length to penalize")
    
    # XTC (Extended Temperature Control)
    xtc_enabled: Optional[bool] = Field(None, description="Enable XTC temperature control")
    xtc_temperature_min: Optional[float] = Field(None, ge=0.0, le=2.0, description="XTC minimum temperature")
    xtc_temperature_max: Optional[float] = Field(None, ge=0.0, le=2.0, description="XTC maximum temperature")
    xtc_adaptation_rate: Optional[float] = Field(None, ge=0.0, le=1.0, description="XTC adaptation rate")
    
    # Dynamic Temperature
    dynamic_temp_enabled: Optional[bool] = Field(None, description="Enable dynamic temperature")
    dynamic_temp_schedule: Optional[str] = Field(None, pattern="^(linear|exponential|cosine)$", description="Dynamic temperature schedule")
    dynamic_temp_range: Optional[List[float]] = Field(None, min_length=2, max_length=2, description="Dynamic temperature range [min, max]")
    
    # Repetition Penalty Block
    rep_penalty_range: Optional[int] = Field(None, ge=0, description="Repetition penalty block range (token count)")
    rep_penalty_slope: Optional[float] = Field(None, ge=0.0, description="Repetition penalty block slope")
    rep_penalty_alpha: Optional[float] = Field(None, ge=0.0, description="Repetition penalty block alpha")


class AISettings(BaseModel):
    """AI settings schema combining sampler and persona settings."""
    # Sampler settings (flattened for easier access)
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.9, ge=0.0, le=1.0, description="Top-p sampling")
    top_k: int = Field(40, ge=0, description="Top-k sampling")
    min_p: float = Field(0.0, ge=0.0, le=1.0, description="Minimum probability threshold")
    repeat_penalty: float = Field(1.1, ge=1.0, le=2.0, description="Repeat penalty")
    presence_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="Presence penalty")
    frequency_penalty: float = Field(0.0, ge=-2.0, le=2.0, description="Frequency penalty")
    typical_p: float = Field(1.0, ge=0.0, le=1.0, description="Typical sampling")
    tfs_z: float = Field(1.0, ge=0.0, description="Tail-free sampling")
    mirostat_mode: int = Field(0, ge=0, le=2, description="Mirostat mode")
    mirostat_tau: float = Field(5.0, ge=0.0, le=10.0, description="Mirostat tau")
    mirostat_eta: float = Field(0.1, ge=0.0, le=1.0, description="Mirostat eta")
    max_tokens: int = Field(512, ge=-1, le=32768, description="Max tokens")
    stop: Optional[List[str]] = Field(None, description="Stop sequences (JSON array of strings)")
    
    # Advanced Samplers
    # DRY (Dynamic Repetition Penalty) - sequence-based repetition control
    dry_multiplier: Optional[float] = Field(None, ge=0.0, description="DRY multiplier: penalty strength (0.0=disabled)")
    dry_base: Optional[float] = Field(None, ge=0.0, description="DRY base: penalty scaling factor for sequence length")
    dry_allowed_length: Optional[int] = Field(None, ge=0, description="DRY allowed length: minimum sequence length to penalize")
    xtc_enabled: Optional[bool] = Field(None, description="Enable XTC temperature control")
    xtc_temperature_min: Optional[float] = Field(None, ge=0.0, le=2.0, description="XTC minimum temperature")
    xtc_temperature_max: Optional[float] = Field(None, ge=0.0, le=2.0, description="XTC maximum temperature")
    xtc_adaptation_rate: Optional[float] = Field(None, ge=0.0, le=1.0, description="XTC adaptation rate")
    dynamic_temp_enabled: Optional[bool] = Field(None, description="Enable dynamic temperature")
    dynamic_temp_schedule: Optional[str] = Field(None, description="Dynamic temperature schedule (linear/exponential/cosine)")
    dynamic_temp_range: Optional[List[float]] = Field(None, description="Dynamic temperature range [min, max]")
    rep_penalty_range: Optional[int] = Field(None, ge=0, description="Repetition penalty block range")
    rep_penalty_slope: Optional[float] = Field(None, ge=0.0, description="Repetition penalty block slope")
    rep_penalty_alpha: Optional[float] = Field(None, ge=0.0, description="Repetition penalty block alpha")
    
    # Persona settings
    system_prompt: Optional[str] = Field(None, description="System prompt")
    character_card: Optional[CharacterCard] = Field(None, description="Character card for personality")
    user_profile: Optional[UserProfile] = Field(None, description="User profile information")
    default_load_options: Optional[ModelLoadOptions] = Field(None, description="Default model loading options")
    
    # Remote LLM Endpoint Settings
    llm_endpoint_mode: Optional[str] = Field("local", description="LLM endpoint mode: 'local' or 'remote'")
    llm_remote_url: Optional[str] = Field(None, description="Remote OpenAI-compatible endpoint URL (e.g., https://api.openai.com/v1)")
    llm_remote_api_key: Optional[str] = Field(None, description="API key for remote endpoint (optional)")
    llm_remote_model: Optional[str] = Field(None, description="Model name/ID to use with remote endpoint")

    # Streaming Mode Settings
    streaming_mode: str = Field("non-streaming", description="Streaming mode: 'streaming' (real-time, no tool calling), 'non-streaming' (with tool calling), 'experimental' (auto-detect)")


class AISettingsResponse(BaseModel):
    """AI settings response schema."""
    model_config = ConfigDict(protected_namespaces=())
    
    settings: AISettings
    model_loaded: bool
    current_model: Optional[str] = None
    supports_tool_calling: bool = False


class ModelInfo(BaseModel):
    """Model information schema."""
    model_config = ConfigDict(protected_namespaces=())
    
    model_id: str
    name: str
    size: Optional[str] = None
    format: str = "gguf"
    downloaded: bool = False
    # Enhanced metadata from model_info.json
    repo_id: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    huggingface_url: Optional[str] = None
    downloaded_at: Optional[str] = None
    has_metadata: bool = False
    moe: Optional[Dict[str, Any]] = None  # MoE configuration from model_info.json
    supports_tool_calling: Optional[bool] = None


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
