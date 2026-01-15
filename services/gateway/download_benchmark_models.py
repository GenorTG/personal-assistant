#!/usr/bin/env python3
"""Download benchmark models for function calling testing.

Downloads all models mentioned in the llama.cpp function calling documentation:
https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
"""

import sys
import asyncio
from pathlib import Path
import logging
import json

# Determine project root and data directory
script_dir = Path(__file__).parent.resolve()
project_root = script_dir.parent.parent  # gateway -> services -> project root
data_dir = project_root / "data"
models_dir = data_dir / "models"

# Ensure models directory exists
models_dir.mkdir(parents=True, exist_ok=True)

# Add gateway src to path for utilities that don't need full settings
sys.path.insert(0, str(script_dir / "src"))

# Import utilities that don't require settings
try:
    from src.utils.get_chat_template import get_chat_template
except ImportError:
    # Fallback: import directly
    sys.path.insert(0, str(script_dir))
    from src.utils.get_chat_template import get_chat_template

# For downloading, we'll use huggingface_hub directly
try:
    from huggingface_hub import hf_hub_download, HfApi
except ImportError:
    print("Error: huggingface_hub is required. Install with: pip install huggingface_hub")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Benchmark models from the documentation
# Note: Filenames may need to be adjusted based on actual repo contents
BENCHMARK_MODELS = [
    # Native support models
    {
        "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "filename": None,  # Will auto-detect
        "name": "Qwen 2.5 7B Instruct",
        "template_override": None,  # Native support
        "preferred_quant": "Q4_K_M",  # Preferred quantization
    },
    {
        "repo_id": "bartowski/Mistral-Nemo-Instruct-2407-GGUF",
        "filename": None,
        "name": "Mistral Nemo Instruct",
        "template_override": None,
        "preferred_quant": "Q6_K_L",
    },
    {
        "repo_id": "bartowski/Llama-3.3-70B-Instruct-GGUF",
        "filename": None,
        "name": "Llama 3.3 70B Instruct",
        "template_override": None,
        "preferred_quant": "Q4_K_M",
    },
    # Models requiring template overrides
    {
        "repo_id": "bartowski/functionary-small-v3.2-GGUF",
        "filename": None,
        "name": "Functionary Small v3.2",
        "template_override": "meetkai-functionary-medium-v3.2.jinja",
        "preferred_quant": "Q4_K_M",
    },
    {
        "repo_id": "bartowski/Hermes-2-Pro-Llama-3-8B-GGUF",
        "filename": None,
        "name": "Hermes 2 Pro Llama 3 8B",
        "template_override": "NousResearch-Hermes-2-Pro-Llama-3-8B-tool_use.jinja",
        "preferred_quant": "Q4_K_M",
    },
    {
        "repo_id": "bartowski/Hermes-3-Llama-3.1-8B-GGUF",
        "filename": None,
        "name": "Hermes 3 Llama 3.1 8B",
        "template_override": "NousResearch-Hermes-3-Llama-3.1-8B-tool_use.jinja",
        "preferred_quant": "Q4_K_M",
    },
    {
        "repo_id": "bartowski/firefunction-v2-GGUF",
        "filename": None,
        "name": "Firefunction v2",
        "template_override": "fireworks-ai-llama-3-firefunction-v2.jinja",
        "preferred_quant": "IQ1_M",
    },
    {
        "repo_id": "bartowski/c4ai-command-r7b-12-2024-GGUF",
        "filename": None,
        "name": "Command R7B",
        "template_override": "CohereForAI-c4ai-command-r7b-12-2024-tool_use.jinja",
        "preferred_quant": "Q6_K_L",
    },
    # DeepSeek R1 models (need custom template)
    {
        "repo_id": "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        "filename": None,
        "name": "DeepSeek R1 Distill Qwen 7B",
        "template_override": "llama-cpp-deepseek-r1.jinja",
        "preferred_quant": "Q6_K_L",
    },
    {
        "repo_id": "bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF",
        "filename": None,
        "name": "DeepSeek R1 Distill Qwen 32B",
        "template_override": "llama-cpp-deepseek-r1.jinja",
        "preferred_quant": "Q4_K_M",
    },
    # Generic format support models
    {
        "repo_id": "bartowski/phi-4-GGUF",
        "filename": None,
        "name": "Phi-4",
        "template_override": None,
        "preferred_quant": "Q4_0",
    },
    {
        "repo_id": "bartowski/gemma-2-2b-it-GGUF",
        "filename": None,
        "name": "Gemma 2 2B IT",
        "template_override": None,
        "preferred_quant": "Q8_0",
    },
    {
        "repo_id": "bartowski/c4ai-command-r-v01-GGUF",
        "filename": None,
        "name": "Command R v01",
        "template_override": None,
        "preferred_quant": "Q2_K",
    },
]


async def download_model_with_template(
    model_config: dict,
    progress_callback=None
) -> bool:
    """Download a model and fetch/save its chat template.
    
    Args:
        model_config: Model configuration dict
        progress_callback: Optional progress callback
        
    Returns:
        True if successful, False otherwise
    """
    repo_id = model_config["repo_id"]
    filename = model_config.get("filename")
    name = model_config["name"]
    preferred_quant = model_config.get("preferred_quant")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Downloading: {name}")
    logger.info(f"Repository: {repo_id}")
    logger.info(f"{'='*60}")
    
    try:
        # Ensure models directory exists
        models_dir.mkdir(parents=True, exist_ok=True)
        
        # If filename not specified, find the best match
        if not filename:
            logger.info("Finding available GGUF files in repository...")
            loop = asyncio.get_event_loop()
            
            def list_files():
                api = HfApi()
                files = api.list_repo_files(repo_id, repo_type="model")
                return [f for f in files if f.endswith(".gguf")]
            
            available_files = await loop.run_in_executor(None, list_files)
            
            if not available_files:
                logger.error(f"No GGUF files found in {repo_id}")
                return False
            
            # Try to find preferred quantization
            if preferred_quant:
                matching = [f for f in available_files if preferred_quant.upper() in f.upper()]
                if matching:
                    filename = matching[0]
                    logger.info(f"Found preferred quantization: {filename}")
                else:
                    # Sort and pick first (usually smallest/reasonable size)
                    available_files.sort()
                    filename = available_files[0]
                    logger.info(f"Preferred quantization not found, using: {filename}")
            else:
                available_files.sort()
                filename = available_files[0]
                logger.info(f"Using first available file: {filename}")
        
        logger.info(f"Downloading: {filename}")
        
        # Download the model using huggingface_hub
        loop = asyncio.get_event_loop()
        model_path = await loop.run_in_executor(
            None,
            lambda: hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=models_dir
            )
        )
        model_path = Path(model_path)
        logger.info(f"✓ Downloaded: {model_path}")
        
        # Fetch and save chat template
        # For GGUF repos, try to get template from base model repo
        try:
            # Extract base model name from repo_id (remove -GGUF suffix)
            base_repo_id = repo_id.replace("-GGUF", "").replace("_GGUF", "")
            # Try original repo first, then base model
            template_repo_ids = [repo_id, base_repo_id]
            
            template = None
            for template_repo in template_repo_ids:
                try:
                    logger.info(f"Fetching chat template from {template_repo}...")
                    template = get_chat_template(template_repo)
                    logger.info(f"✓ Found template in {template_repo}")
                    break
                except Exception as e:
                    logger.debug(f"Template not found in {template_repo}: {e}")
                    continue
            
            if not template:
                # Try common base model patterns
                if "bartowski" in repo_id:
                    # Extract model name and try common base repos
                    model_name = repo_id.split("/")[-1].replace("-GGUF", "").replace("_GGUF", "")
                    # Try Qwen base models
                    if "Qwen" in model_name:
                        base_models = [
                            model_name.replace("-Instruct", ""),
                            "Qwen/Qwen2.5-7B-Instruct",
                            "Qwen/Qwen2.5-1.5B-Instruct"
                        ]
                        for base in base_models:
                            try:
                                template = get_chat_template(base)
                                logger.info(f"✓ Found template in base model: {base}")
                                break
                            except:
                                continue
                
                if not template:
                    raise Exception("Could not find template in any repository")
            
            # Save template next to model file
            if model_path.is_file():
                template_file = model_path.parent / f"{model_path.stem}.jinja"
            else:
                template_file = model_path / f"{model_path.name}.jinja"
            
            template_file.parent.mkdir(parents=True, exist_ok=True)
            with open(template_file, 'w', encoding='utf-8') as f:
                f.write(template)
            
            logger.info(f"✓ Saved chat template to: {template_file}")
            
            # If template override is specified, note it
            if model_config.get("template_override"):
                logger.info(f"  Note: This model may need template override: {model_config['template_override']}")
                logger.info(f"  Template file saved, but you may need to use the override from llama.cpp templates")
            
        except Exception as e:
            logger.warning(f"⚠ Could not fetch/save chat template: {e}")
            logger.info("  Template may be available in GGUF metadata or may need manual override")
        
        # Save model_info.json with repo_id
        try:
            metadata_file = model_path.parent / "model_info.json" if model_path.is_file() else model_path / "model_info.json"
            metadata = {
                "repo_id": repo_id,
                "name": name,
                "filename": filename,
            }
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ Saved model metadata to: {metadata_file}")
        except Exception as e:
            logger.warning(f"⚠ Could not save model metadata: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to download {name}: {e}")
        return False


async def download_all_benchmark_models(selected_models: list = None) -> dict:
    """Download all benchmark models.
    
    Args:
        selected_models: Optional list of model indices to download (None = all)
        
    Returns:
        Dict with download results
    """
    models_to_download = BENCHMARK_MODELS
    if selected_models is not None:
        models_to_download = [BENCHMARK_MODELS[i] for i in selected_models if i < len(BENCHMARK_MODELS)]
    
    results = {
        "total": len(models_to_download),
        "successful": 0,
        "failed": 0,
        "failed_models": []
    }
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Downloading {len(models_to_download)} benchmark model(s)")
    logger.info(f"{'='*60}\n")
    
    for i, model_config in enumerate(models_to_download, 1):
        logger.info(f"\n[{i}/{len(models_to_download)}]")
        success = await download_model_with_template(model_config)
        
        if success:
            results["successful"] += 1
        else:
            results["failed"] += 1
            results["failed_models"].append(model_config["name"])
    
    logger.info(f"\n{'='*60}")
    logger.info("Download Summary:")
    logger.info(f"  Total: {results['total']}")
    logger.info(f"  Successful: {results['successful']}")
    logger.info(f"  Failed: {results['failed']}")
    if results["failed_models"]:
        logger.info(f"  Failed models: {', '.join(results['failed_models'])}")
    logger.info(f"{'='*60}\n")
    
    return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Download benchmark models for function calling testing"
    )
    parser.add_argument(
        '--models',
        type=int,
        nargs='+',
        help='Download specific models by index (0-based). If not specified, downloads all.'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available benchmark models and exit'
    )
    
    args = parser.parse_args()
    
    if args.list:
        logger.info("Available benchmark models:")
        for i, model in enumerate(BENCHMARK_MODELS):
            logger.info(f"  [{i}] {model['name']} - {model['repo_id']}")
        return
    
    try:
        results = asyncio.run(download_all_benchmark_models(args.models))
        sys.exit(0 if results["failed"] == 0 else 1)
    except KeyboardInterrupt:
        logger.info("\nDownload cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
