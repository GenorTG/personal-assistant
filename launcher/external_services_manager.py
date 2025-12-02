#!/usr/bin/env python3
"""
External Services Manager
Handles automatic cloning, setup, and management of external Git repositories
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class ExternalServicesManager:
    """Manages external Git-based services."""
    
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.external_services_dir = root_dir / "external_services"
        self.metadata_file = self.external_services_dir / ".services_metadata.json"
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata about external services."""
        if self.metadata_file.exists():
            try:
                # Check if file is empty
                if self.metadata_file.stat().st_size == 0:
                    logger.warning("Metadata file is empty, resetting to empty dict")
                    return {}
                    
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        logger.warning("Metadata file has no content, resetting to empty dict")
                        return {}
                    return json.loads(content)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Metadata file corrupted, resetting: {e}")
                # Try to delete corrupted file
                try:
                    self.metadata_file.unlink()
                except Exception:
                    pass
                return {}
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
        return {}
    
    def _save_metadata(self):
        """Save metadata about external services."""
        try:
            self.external_services_dir.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def ensure_service_cloned(
        self, 
        repo_url: str, 
        service_name: str, 
        target_dir: Path,
        branch: str = "main"
    ) -> bool:
        """
        Ensure an external service repository is cloned.
        
        Args:
            repo_url: Git repository URL
            service_name: Name identifier for the service
            target_dir: Target directory for the clone
            branch: Git branch to checkout (default: main)
        
        Returns:
            True if service is available (already exists or successfully cloned)
        """
        # Check if already cloned
        if target_dir.exists() and (target_dir / ".git").exists():
            logger.info(f"Service {service_name} already cloned at {target_dir}")
            return True
        
        # Ensure parent directory exists
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Cloning {service_name} from {repo_url}...")
        
        try:
            # Clone the repository
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(target_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to clone {service_name}: {result.stderr}")
                return False
            
            logger.info(f"Successfully cloned {service_name}")
            
            # Get commit info
            commit_hash = self._get_commit_hash(target_dir)
            
            # Save metadata
            self.metadata[service_name] = {
                "repo_url": repo_url,
                "target_dir": str(target_dir),
                "branch": branch,
                "commit_hash": commit_hash,
                "cloned_at": subprocess.run(
                    ["date", "+%Y-%m-%d %H:%M:%S"],
                    capture_output=True,
                    text=True,
                    shell=True
                ).stdout.strip()
            }
            self._save_metadata()
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout cloning {service_name}")
            return False
        except FileNotFoundError:
            logger.error("Git not found. Please install Git to clone external services.")
            return False
        except Exception as e:
            logger.error(f"Error cloning {service_name}: {e}")
            return False
    
    def _get_commit_hash(self, repo_dir: Path) -> Optional[str]:
        """Get current commit hash of a repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get commit hash: {e}")
        return None
    
    def setup_service(self, service_name: str, target_dir: Path) -> bool:
        """
        Setup a cloned service (copy .env, run initial configuration).
        
        Args:
            service_name: Name of the service
            target_dir: Directory where service is cloned
        
        Returns:
            True if setup successful
        """
        logger.info(f"Setting up {service_name}...")
        
        # Check for .env.example and create .env if it doesn't exist
        env_example = target_dir / ".env.example"
        env_file = target_dir / ".env"
        
        if env_example.exists() and not env_file.exists():
            try:
                shutil.copy(env_example, env_file)
                logger.info(f"Created .env from .env.example for {service_name}")
            except Exception as e:
                logger.error(f"Failed to create .env: {e}")
                return False
        
        # For Chatterbox specifically, check for .env.example.docker as well
        env_example_docker = target_dir / ".env.example.docker"
        if service_name == "chatterbox" and env_example_docker.exists() and not env_file.exists():
            try:
                # Use .env.example instead of .env.example.docker for local setup
                if env_example.exists():
                    shutil.copy(env_example, env_file)
                    logger.info(f"Created .env from .env.example for local Chatterbox setup")
            except Exception as e:
                logger.error(f"Failed to create .env: {e}")
        
        logger.info(f"Setup complete for {service_name}")
        return True
    
    def update_service(self, service_name: str, target_dir: Path) -> bool:
        """
        Update an external service repository (git pull).
        
        Args:
            service_name: Name of the service
            target_dir: Directory where service is cloned
        
        Returns:
            True if update successful
        """
        if not (target_dir / ".git").exists():
            logger.error(f"Service {service_name} is not a git repository")
            return False
        
        logger.info(f"Updating {service_name}...")
        
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to update {service_name}: {result.stderr}")
                return False
            
            logger.info(f"Successfully updated {service_name}")
            
            # Update metadata
            commit_hash = self._get_commit_hash(target_dir)
            if service_name in self.metadata:
                self.metadata[service_name]["commit_hash"] = commit_hash
                self.metadata[service_name]["updated_at"] = subprocess.run(
                    ["date", "+%Y-%m-%d %H:%M:%S"],
                    capture_output=True,
                    text=True,
                    shell=True
                ).stdout.strip()
                self._save_metadata()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating {service_name}: {e}")
            return False
    
    def get_service_info(self, service_name: str, target_dir: Path) -> Dict[str, Any]:
        """
        Get information about an external service.
        
        Args:
            service_name: Name of the service
            target_dir: Directory where service is cloned
        
        Returns:
            Dictionary with service information
        """
        info = {
            "name": service_name,
            "exists": target_dir.exists(),
            "is_git_repo": (target_dir / ".git").exists(),
            "path": str(target_dir)
        }
        
        if info["is_git_repo"]:
            # Get current branch
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    info["branch"] = result.stdout.strip()
            except Exception:
                pass
            
            # Get commit hash
            info["commit_hash"] = self._get_commit_hash(target_dir)
            
            # Check for uncommitted changes
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    info["has_uncommitted_changes"] = bool(result.stdout.strip())
            except Exception:
                pass
        
        # Add metadata if available
        if service_name in self.metadata:
            info["metadata"] = self.metadata[service_name]
        
        return info
    
    def remove_service(self, service_name: str, target_dir: Path) -> bool:
        """
        Remove an external service (delete directory).
        
        Args:
            service_name: Name of the service
            target_dir: Directory to remove
        
        Returns:
            True if removal successful
        """
        if not target_dir.exists():
            logger.info(f"Service {service_name} directory does not exist")
            return True
        
        logger.info(f"Removing {service_name}...")
        
        try:
            shutil.rmtree(target_dir)
            logger.info(f"Successfully removed {service_name}")
            
            # Remove from metadata
            if service_name in self.metadata:
                del self.metadata[service_name]
                self._save_metadata()
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing {service_name}: {e}")
            return False
