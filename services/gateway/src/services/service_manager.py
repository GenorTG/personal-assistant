import logging
import httpx
from typing import Optional, Dict, Any

from ..config.settings import settings

logger = logging.getLogger(__name__)

class RemoteModelDownloader:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.models_dir = None # Not available locally

    async def search_models(self, query: str, limit: int = 20):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/api/models/search", params={"query": query, "limit": limit})
            if resp.status_code == 200:
                return resp.json()
            return []

    async def download_model(self, repo_id: str, filename: Optional[str] = None):
        async with httpx.AsyncClient(timeout=None) as client: # No timeout for download
            params = {"repo_id": repo_id}
            if filename: params["filename"] = filename
            resp = await client.post(f"{self.base_url}/api/models/download", params=params)
            if resp.status_code == 200:
                return resp.json().get("path")
            raise RuntimeError(f"Download failed: {resp.text}")

    def list_downloaded_models(self):
        # Synchronous wrapper for async call - this is tricky in sync context
        # For now, we'll return empty list or need to make this async in routes
        # But routes.py calls this synchronously in list_models
        # We might need to change routes.py to await this, or use a sync client here
        # Let's use sync client for list_downloaded_models as it's called synchronously
        import httpx
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/api/models")
                if resp.status_code == 200:
                    data = resp.json()
                    from pathlib import Path
                    return [Path(m["path"]) for m in data]
                else:
                    logger.warning(f"LLM service /api/models returned status {resp.status_code}")
                    return []
        except httpx.ConnectError as e:
            logger.warning(f"LLM service not accessible: {e}")
            return []
        except httpx.TimeoutException:
            logger.warning(f"LLM service /api/models request timed out")
            return []
        except Exception as e:
            logger.error(f"Error fetching models from LLM service: {e}")
            return []

    def get_model_info(self, model_path):
        # Mock info for now as remote extraction is complex
        return {
            "name": str(model_path),
            "size_gb": 0,
            "size_mb": 0,
            "quantization": "unknown"
        }
        
    def delete_model(self, model_id: str):
        import httpx
        with httpx.Client() as client:
            resp = client.delete(f"{self.base_url}/api/models/{model_id}")
            return resp.status_code == 200

    async def get_model_files(self, repo_id: str):
        # This usually calls HuggingFace API directly, so we can implement it locally
        # or proxy it. Implementing locally is easier if we have huggingface_hub
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            files = api.list_repo_files(repo_id=repo_id)
            return [f for f in files if f.endswith(".gguf")]
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []


class RemoteLLMManager:
    """Mimics LLMManager but calls remote service."""
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
        self.current_model_name = None
        self.loader = type('MockLoader', (), {'_gpu_layers': -1, '_n_ctx': 4096})()
        self.downloader = RemoteModelDownloader(base_url)
        self.default_load_options = {
            "n_gpu_layers": -1,
            "n_ctx": 4096,
            "use_flash_attention": False
        }
        self.model_configs = {}
        self._load_model_configs()
        
    def _load_model_configs(self):
        try:
            config_path = settings.data_dir / "model_configs.json"
            if config_path.exists():
                import json
                with open(config_path, 'r') as f:
                    self.model_configs = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load model configs: {e}")
            self.model_configs = {}

    def _save_model_configs(self):
        try:
            config_path = settings.data_dir / "model_configs.json"
            import json
            with open(config_path, 'w') as f:
                json.dump(self.model_configs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save model configs: {e}")

    def get_model_config(self, model_id: str) -> Dict[str, Any]:
        return self.model_configs.get(model_id, {})

    def save_model_config(self, model_id: str, config: Dict[str, Any]):
        self.model_configs[model_id] = config
        self._save_model_configs()

    async def is_model_loaded(self) -> bool:
        try:
            resp = await self.client.get("/v1/models")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    self.current_model_name = data[0]["id"]
                    return True
            return False
        except:
            return False
            
    def get_current_model_path(self) -> Optional[str]:
        return self.current_model_name
        
    def get_settings(self) -> Dict[str, Any]:
        return {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1
        }
        
    def update_settings(self, settings: Dict[str, Any]):
        pass
        
    def get_system_prompt(self) -> str:
        return ""
        
    def get_character_card(self):
        return None
        
    def get_user_profile(self):
        return None
        
    def update_character_card(self, card):
        pass
        
    def update_user_profile(self, profile):
        pass
        
    def get_default_load_options(self) -> Dict[str, Any]:
        return self.default_load_options
        
    def update_default_load_options(self, options: Dict[str, Any]):
        self.default_load_options.update(options)
    
    async def load_model(self, model_path, **kwargs):
        # 1. Start with global defaults
        load_params = self.default_load_options.copy()
        
        # 2. Apply per-model config if exists
        # Extract model ID from path (filename)
        from pathlib import Path
        model_id = Path(model_path).name
        if model_id in self.model_configs:
            load_params.update(self.model_configs[model_id])
            
        # 3. Apply request overrides (kwargs)
        load_params.update(kwargs)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {"model_path": model_path, **load_params}
            resp = await client.post(f"{self.base_url}/api/models/load", json=payload)
            return resp.status_code == 200

    async def unload_model(self):
        async with httpx.AsyncClient() as client:
            await client.post(f"{self.base_url}/api/models/unload")


class ServiceManager:
    """Manages connections to microservices."""
    
    def __init__(self):
        self.llm_service_url = "http://localhost:8001"
        self.speech_service_url = "http://localhost:8003"
        self.tts_service_url = "http://localhost:8880"
        
        self.llm_manager = RemoteLLMManager(self.llm_service_url)
        self.chat_manager = None
        self.memory_store = None
        self.tool_manager = None # Renamed from tool_registry
        self.stt_service = None # Remote STT
        self.tts_service = None # Remote TTS
        self.status_manager = None # Service status monitoring
        
    async def initialize(self):
        """Initialize services."""
        from .chat.manager import ChatManager
        from .memory.store import MemoryStore
        from .tools.manager import ToolManager # Use ToolManager
        from .status_manager import ServiceStatusManager
        
        # Initialize Core Components
        self.memory_store = MemoryStore()
        await self.memory_store.initialize()
        
        self.tool_manager = ToolManager()
        
        # Initialize Chat Manager
        self.chat_manager = ChatManager(self, self.memory_store, self.tool_manager) # Pass tool_manager
        
        # Initialize TTS Service
        from .tts.service import TTSService
        self.tts_service = TTSService()
        
        # STT Service - Always enable RemoteSTT proxy
        # The actual service availability is checked at runtime
        self.stt_service = type('RemoteSTT', (), {
            'provider': 'Whisper',
            '_initialized': True,
            'transcribe': self._remote_transcribe
        })()
        logger.info("STT Service proxy initialized (always on)")
        
        # Initialize and start Service Status Manager
        self.status_manager = ServiceStatusManager()
        
        # Run initializations in parallel to speed up startup
        import asyncio
        
        async def init_tts():
            # Load saved backend selection or default to pyttsx3
            saved_backend = await self.memory_store.get_setting("tts_backend", "pyttsx3")
            await self.tts_service.switch_backend(saved_backend)
            logger.info(f"TTS Service initialized with backend: {saved_backend}")
            
        async def init_status():
            await self.status_manager.start()
            logger.info("Service status manager started")
            
        # Execute parallel initialization
        await asyncio.gather(
            init_tts(),
            init_status()
        )
        
        logger.info("Gateway Services Initialized")

    def enable_stt(self):
        """Enable STT service on demand."""
        if self.stt_service:
            return
            
        self.stt_service = type('RemoteSTT', (), {
            'provider': 'Whisper',
            '_initialized': True,
            'transcribe': self._remote_transcribe
        })()
        logger.info("STT Service enabled on demand")


    async def _remote_transcribe(self, audio_path, language=None):
        # Read file
        import aiofiles
        async with aiofiles.open(audio_path, 'rb') as f:
            data = await f.read()
        
        async with httpx.AsyncClient() as client:
            files = {'file': ('audio.wav', data, 'audio/wav')}
            resp = await client.post(f"{self.speech_service_url}/v1/audio/transcriptions", files=files)
            if resp.status_code == 200:
                return resp.json().get("text"), resp.json().get("language")
            raise RuntimeError(f"STT Error: {resp.text}")

    async def _remote_synthesize(self, text, voice=None, output_format="wav"):
        async with httpx.AsyncClient() as client:
            payload = {"input": text, "voice": voice}
            # Default to Kokoro
            resp = await client.post(f"{self.tts_service_url}/v1/audio/speech", json=payload)
            if resp.status_code == 200:
                return resp.content
            raise RuntimeError(f"TTS Error: {resp.text}")

    # Interface for ChatManager to call LLM
    async def generate_response(self, messages, settings=None, **kwargs):
        """Call LLM Service."""
        async with httpx.AsyncClient() as client:
            payload = {
                "messages": messages,
                **kwargs
            }
            if settings:
                payload.update(settings)
                
            response = await client.post(f"{self.llm_service_url}/v1/chat/completions", json=payload, timeout=120.0)
            if response.status_code != 200:
                raise RuntimeError(f"LLM Service Error: {response.text}")
                
            data = response.json()
            return {
                "response": data["choices"][0]["message"]["content"],
                "tool_calls": data["choices"][0]["message"].get("tool_calls")
            }

service_manager = ServiceManager()
