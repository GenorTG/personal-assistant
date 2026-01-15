#!/usr/bin/env python3
"""Migrate data from services/data to data/ folder.

This script consolidates the data folders by moving all data from
services/data/ to data/ at the project root.
"""

import sys
import shutil
from pathlib import Path
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_data_folders(project_root: Path, dry_run: bool = False) -> dict:
    """Migrate data from services/data to data/.
    
    Args:
        project_root: Path to project root directory
        dry_run: If True, only show what would be migrated without actually doing it
        
    Returns:
        Dict with migration results
    """
    services_data = project_root / "services" / "data"
    root_data = project_root / "data"
    
    results = {
        "files_copied": 0,
        "files_skipped": 0,
        "conflicts": [],
        "errors": []
    }
    
    if not services_data.exists():
        logger.info(f"Source directory {services_data} does not exist. Nothing to migrate.")
        return results
    
    logger.info(f"Source: {services_data}")
    logger.info(f"Destination: {root_data}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'MIGRATE'}")
    logger.info("")
    
    # Create destination if it doesn't exist
    if not dry_run:
        root_data.mkdir(parents=True, exist_ok=True)
    
    # Walk through all files in services/data
    for source_path in services_data.rglob("*"):
        if source_path.is_dir():
            continue
        
        # Calculate relative path
        try:
            relative_path = source_path.relative_to(services_data)
            dest_path = root_data / relative_path
        except ValueError as e:
            logger.warning(f"Could not calculate relative path for {source_path}: {e}")
            results["errors"].append(str(source_path))
            continue
        
        # Check if destination exists
        if dest_path.exists():
            # Compare file modification times
            source_mtime = source_path.stat().st_mtime
            dest_mtime = dest_path.stat().st_mtime
            
            if source_mtime > dest_mtime:
                # Source is newer
                logger.info(f"Conflict: {relative_path} (source is newer)")
                results["conflicts"].append({
                    "path": str(relative_path),
                    "action": "source_newer",
                    "source_mtime": datetime.fromtimestamp(source_mtime).isoformat(),
                    "dest_mtime": datetime.fromtimestamp(dest_mtime).isoformat()
                })
                if not dry_run:
                    try:
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, dest_path)
                        results["files_copied"] += 1
                        logger.info(f"  → Copied (source is newer)")
                    except Exception as e:
                        logger.error(f"  ✗ Error copying: {e}")
                        results["errors"].append(str(source_path))
            else:
                # Destination is newer or same
                logger.info(f"Skipped: {relative_path} (destination is newer or same)")
                results["files_skipped"] += 1
        else:
            # Destination doesn't exist, copy file
            logger.info(f"Copying: {relative_path}")
            if not dry_run:
                try:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    results["files_copied"] += 1
                    logger.info(f"  ✓ Copied")
                except Exception as e:
                    logger.error(f"  ✗ Error copying: {e}")
                    results["errors"].append(str(source_path))
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration Summary:")
    logger.info(f"  Files copied: {results['files_copied']}")
    logger.info(f"  Files skipped: {results['files_skipped']}")
    logger.info(f"  Conflicts: {len(results['conflicts'])}")
    logger.info(f"  Errors: {len(results['errors'])}")
    logger.info("=" * 60)
    
    if results["conflicts"]:
        logger.info("")
        logger.info("Conflicts (source was newer and was copied):")
        for conflict in results["conflicts"]:
            logger.info(f"  - {conflict['path']}")
    
    if results["errors"]:
        logger.info("")
        logger.warning("Errors occurred:")
        for error in results["errors"]:
            logger.warning(f"  - {error}")
    
    return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate data from services/data to data/ folder"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually doing it'
    )
    parser.add_argument(
        '--project-root',
        type=str,
        default=None,
        help='Project root directory (default: current directory)'
    )
    
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        # Assume script is in scripts/ directory
        script_dir = Path(__file__).parent.resolve()
        project_root = script_dir.parent
    
    logger.info(f"Project root: {project_root}")
    logger.info("")
    
    try:
        results = migrate_data_folders(project_root, dry_run=args.dry_run)
        
        if args.dry_run:
            logger.info("")
            logger.info("This was a dry run. No files were actually migrated.")
            logger.info("Run without --dry-run to perform the migration.")
        else:
            logger.info("")
            logger.info("Migration complete!")
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Verify all data was migrated correctly")
            logger.info("  2. Update settings.py to use new data_dir path")
            logger.info("  3. Test that services can access data from new location")
            logger.info("  4. Remove services/data/ directory after verification")
        
        sys.exit(0 if len(results["errors"]) == 0 else 1)
    except KeyboardInterrupt:
        logger.info("\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
