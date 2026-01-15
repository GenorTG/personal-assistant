#!/usr/bin/env python3
"""Delete all existing models to prepare for benchmark model downloads.

This script removes all currently downloaded models to ensure a clean
testing environment with only benchmark models from the documentation.
"""

import sys
from pathlib import Path
import logging
import shutil

# Determine project root and data directory
script_dir = Path(__file__).parent.resolve()
project_root = script_dir.parent.parent  # gateway -> services -> project root
data_dir = project_root / "data"
models_dir = data_dir / "models"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def delete_all_models(confirm: bool = False) -> int:
    """Delete all existing models.
    
    Args:
        confirm: If True, skip confirmation prompt (for automation)
        
    Returns:
        Number of models deleted
    """
    if not models_dir.exists():
        logger.info(f"Models directory does not exist: {models_dir}")
        return 0
    
    # Find all .gguf files and related metadata
    model_files = list(models_dir.rglob("*.gguf"))
    metadata_files = []
    
    # Also find related .json and .jinja files
    for model_file in model_files:
        # Same directory .json and .jinja files
        metadata_files.append(model_file.parent / f"{model_file.stem}.json")
        metadata_files.append(model_file.parent / f"{model_file.stem}.jinja")
        # model_info.json in same directory
        metadata_files.append(model_file.parent / "model_info.json")
    
    all_files = model_files + [f for f in metadata_files if f.exists()]
    
    if not all_files:
        logger.info("No model files found to delete.")
        return 0
    
    logger.info(f"Found {len(model_files)} model file(s) and {len([f for f in metadata_files if f.exists()])} metadata file(s) to delete:")
    for model_file in model_files:
        logger.info(f"  - {model_file.relative_to(models_dir)}")
    
    if not confirm:
        response = input(f"\nAre you sure you want to delete {len(all_files)} file(s)? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            logger.info("Deletion cancelled.")
            return 0
    
    deleted_count = 0
    deleted_files = []
    
    for file_path in all_files:
        try:
            if file_path.exists():
                file_path.unlink()
                deleted_count += 1
                deleted_files.append(str(file_path.relative_to(models_dir)))
                logger.info(f"✓ Deleted: {file_path.relative_to(models_dir)}")
        except Exception as e:
            logger.error(f"✗ Error deleting {file_path}: {e}")
    
    # Also remove empty directories
    for dir_path in sorted(models_dir.rglob("*"), reverse=True):
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            try:
                dir_path.rmdir()
                logger.info(f"✓ Removed empty directory: {dir_path.relative_to(models_dir)}")
            except Exception:
                pass
    
    logger.info(f"\nDeleted {deleted_count} out of {len(all_files)} file(s).")
    
    if deleted_files:
        logger.info("\nDeleted files:")
        for file_path in deleted_files[:20]:  # Show first 20
            logger.info(f"  - {file_path}")
        if len(deleted_files) > 20:
            logger.info(f"  ... and {len(deleted_files) - 20} more files")
    
    return deleted_count


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Delete all existing models to prepare for benchmark downloads"
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    args = parser.parse_args()
    
    try:
        deleted = delete_all_models(confirm=args.yes)
        sys.exit(0 if deleted >= 0 else 1)
    except KeyboardInterrupt:
        logger.info("\nDeletion cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
