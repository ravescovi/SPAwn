"""
GitHub repository operations for SPAwn.

This module provides functionality for creating and managing GitHub repositories.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import requests

from spawn.config import config

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(
        self,
        token: Optional[str] = None,
        username: Optional[str] = None,
        api_url: str = "https://api.github.com",
    ):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub personal access token. If None, uses the token from config or environment.
            username: GitHub username. If None, uses the username from config or environment.
            api_url: GitHub API URL.
        """
        self.token = token or config.get("github", {}).get("token") or os.environ.get("GITHUB_TOKEN")
        self.username = username or config.get("github", {}).get("username") or os.environ.get("GITHUB_USERNAME")
        self.api_url = api_url
        
        if not self.token:
            logger.warning("No GitHub token provided. Some operations may fail.")
        
        if not self.username:
            logger.warning("No GitHub username provided. Some operations may fail.")
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers for GitHub API requests.

        Returns:
            Dictionary of headers.
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        
        return headers
    
    def create_fork(
        self,
        repo_owner: str,
        repo_name: str,
        new_name: Optional[str] = None,
        organization: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a fork of a GitHub repository.

        Args:
            repo_owner: Owner of the repository to fork.
            repo_name: Name of the repository to fork.
            new_name: New name for the forked repository. If None, uses the original name.
            organization: Organization to create the fork in. If None, creates in the user's account.
            description: Description for the new repository.

        Returns:
            Dictionary with information about the forked repository.

        Raises:
            ValueError: If the fork creation fails.
        """
        if not self.token:
            raise ValueError("GitHub token is required to create a fork")
        
        # Create fork
        fork_url = f"{self.api_url}/repos/{repo_owner}/{repo_name}/forks"
        fork_data = {}
        
        if organization:
            fork_data["organization"] = organization
        
        response = requests.post(fork_url, headers=self._get_headers(), json=fork_data)
        
        if response.status_code != 202:
            raise ValueError(f"Failed to create fork: {response.json().get('message', response.text)}")
        
        fork_info = response.json()
        logger.info(f"Created fork: {fork_info['full_name']}")
        
        # Rename repository if needed
        if new_name and new_name != repo_name:
            owner = organization or self.username
            rename_url = f"{self.api_url}/repos/{owner}/{repo_name}"
            rename_data = {"name": new_name}
            
            if description:
                rename_data["description"] = description
            
            response = requests.patch(rename_url, headers=self._get_headers(), json=rename_data)
            
            if response.status_code != 200:
                logger.warning(f"Failed to rename repository: {response.json().get('message', response.text)}")
            else:
                fork_info = response.json()
                logger.info(f"Renamed repository to: {fork_info['full_name']}")
        
        return fork_info
    
    def configure_pages_and_actions(
        self,
        repo_owner: str,
        repo_name: str,
        branch: str = "gh-pages",
        pages_path: str = "/",
    ) -> None:
        """
        Configure GitHub Actions permissions and enable GitHub Pages deployment.

        Args:
            repo_owner: Owner of the repository.
            repo_name: Name of the repository.
            branch: Branch to deploy from (e.g., 'gh-pages').
            pages_path: Path in the repo to deploy (default is root).
        """
        if not self.token:
            raise ValueError("GitHub token is required to configure repo")

        headers = self._get_headers()

        # Enable Actions with write access
        actions_url = f"{self.api_url}/repos/{repo_owner}/{repo_name}/actions/permissions"
        actions_payload = {
            "enabled": True,
            "allowed_actions": "all",
            "default_workflow_permissions": "write",
        }
        r1 = requests.put(actions_url, headers=headers, json=actions_payload)
        if r1.status_code not in [200, 204]:
            logger.warning(f"Failed to update Actions permissions: {r1.text}")

        # Enable GitHub Pages from branch
        pages_url = f"{self.api_url}/repos/{repo_owner}/{repo_name}/pages"
        pages_payload = {
            "source": {
                "branch": branch,
                "path": pages_path,
            }
        }
        r2 = requests.put(pages_url, headers=headers, json=pages_payload)
        if r2.status_code not in [201, 204]:
            logger.warning(f"Failed to enable GitHub Pages: {r2.text}")
        else:
            logger.info(f"Enabled GitHub Pages for {repo_owner}/{repo_name} from branch {branch}")


    def clone_repository(
        self,
        repo_owner: str,
        repo_name: str,
        target_dir: Optional[Path] = None,
        branch: str = "main",
    ) -> Path:
        """
        Clone a GitHub repository.

        Args:
            repo_owner: Owner of the repository to clone.
            repo_name: Name of the repository to clone.
            target_dir: Directory to clone the repository into. If None, creates a temporary directory.
            branch: Branch to clone.

        Returns:
            Path to the cloned repository.

        Raises:
            ValueError: If the clone fails.
        """
        # Determine target directory
        if target_dir is None:
            target_dir = Path(tempfile.mkdtemp())
        else:
            target_dir = Path(target_dir).expanduser().absolute()
            target_dir.mkdir(parents=True, exist_ok=True)
        
        # Clone repository
        repo_url = f"https://github.com/{repo_owner}/{repo_name}.git"
        
        if self.token:
            # Use token for authentication
            repo_url = f"https://{self.token}@github.com/{repo_owner}/{repo_name}.git"
        
        try:
            subprocess.run(
                ["git", "clone", "--branch", branch, repo_url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"Cloned repository {repo_owner}/{repo_name} to {target_dir}")
            return target_dir
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to clone repository: {e.stderr}")
    
    def push_file(
        self,
        repo_owner: str,
        repo_name: str,
        file_path: str,
        content: Union[str, Dict[str, Any], bytes],
        message: str,
        branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Push a file to a GitHub repository.

        Args:
            repo_owner: Owner of the repository.
            repo_name: Name of the repository.
            file_path: Path to the file in the repository.
            content: Content of the file. Can be a string, dictionary, or bytes.
            message: Commit message.
            branch: Branch to push to.

        Returns:
            Dictionary with information about the commit.

        Raises:
            ValueError: If the push fails.
        """
        if not self.token:
            raise ValueError("GitHub token is required to push files")
        
        # Get the current file to get its SHA
        url = f"{self.api_url}/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        params = {"ref": branch}
        
        response = requests.get(url, headers=self._get_headers(), params=params)
        
        # Prepare content
        if isinstance(content, dict):
            content = json.dumps(content, indent=2)
        
        if isinstance(content, str):
            import base64
            content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        elif isinstance(content, bytes):
            import base64
            content = base64.b64encode(content).decode("utf-8")
        
        # Prepare request data
        data = {
            "message": message,
            "content": content,
            "branch": branch,
        }
        
        # If file exists, add its SHA
        if response.status_code == 200:
            data["sha"] = response.json()["sha"]
        
        # Push file
        response = requests.put(url, headers=self._get_headers(), json=data)
        
        if response.status_code not in [200, 201]:
            raise ValueError(f"Failed to push file: {response.json().get('message', response.text)}")
        
        result = response.json()
        logger.info(f"Pushed file {file_path} to {repo_owner}/{repo_name}")
        
        return result


def fork_template_portal(
    new_name: str,
    description: Optional[str] = None,
    organization: Optional[str] = None,
    token: Optional[str] = None,
    username: Optional[str] = None,
    clone_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Fork the Globus template search portal.

    Args:
        new_name: Name for the forked repository.
        description: Description for the new repository.
        organization: Organization to create the fork in. If None, creates in the user's account.
        token: GitHub personal access token. If None, uses the token from config or environment.
        username: GitHub username. If None, uses the username from config or environment.
        clone_dir: Directory to clone the repository into. If None, doesn't clone the repository.

    Returns:
        Dictionary with information about the forked repository and the path to the cloned repository.
    """
    # Create GitHub client
    client = GitHubClient(token=token, username=username)
    
    # Fork repository
    fork_info = client.create_fork(
        repo_owner="globus",
        repo_name="template-search-portal",
        new_name=new_name,
        organization=organization,
        description=description,
    )
    
    result = {
        "repository": fork_info,
        "clone_path": None,
    }
    
    # Clone repository if requested
    if clone_dir is not None:
        owner = organization or client.username
        clone_path = client.clone_repository(
            repo_owner=owner,
            repo_name=new_name,
            target_dir=clone_dir,
        )
        result["clone_path"] = str(clone_path)
    
    return result


def configure_static_json(
    repo_dir: Union[str, Path],
    index_name: str,
    portal_title: Optional[str] = None,
    portal_subtitle: Optional[str] = None,
    additional_config: Optional[Dict[str, Any]] = None,
    push_to_github: bool = False,
    repo_owner: Optional[str] = None,
    repo_name: Optional[str] = None,
    token: Optional[str] = None,
    username: Optional[str] = None,
    commit_message: str = "Configure portal",
    branch: str = "main",
) -> Path:
    """
    Configure the static.json file in a Globus template search portal repository.

    Args:
        repo_dir: Path to the repository directory.
        index_name: UUID of the Globus Search index.
        portal_title: Title for the portal.
        portal_subtitle: Subtitle for the portal.
        additional_config: Additional configuration to add to the static.json file.
        push_to_github: Whether to push the changes to GitHub.
        repo_owner: Owner of the repository. Required if push_to_github is True.
        repo_name: Name of the repository. Required if push_to_github is True.
        token: GitHub personal access token. If None, uses the token from config or environment.
        username: GitHub username. If None, uses the username from config or environment.
        commit_message: Commit message for the push.
        branch: Branch to push to.

    Returns:
        Path to the configured static.json file.
    """
    repo_dir = Path(repo_dir).expanduser().absolute()
    static_json_path = repo_dir / "static.json"
    
    # Create default configuration
    config_data = {
        "index": {
            "uuid": index_name,
            "name": index_name,
        },
        "branding": {},
    }
    
    # Add portal title and subtitle if provided
    if portal_title:
        config_data["branding"]["title"] = portal_title
    
    if portal_subtitle:
        config_data["branding"]["subtitle"] = portal_subtitle
    
    # Add additional configuration if provided
    if additional_config:
        config_data.update(additional_config)
    
    # Write configuration to static.json
    with open(static_json_path, "w") as f:
        json.dump(config_data, f, indent=2)
    
    logger.info(f"Configured static.json at {static_json_path}")
    
    # Push changes to GitHub if requested
    if push_to_github:
        if not repo_owner or not repo_name:
            raise ValueError("repo_owner and repo_name are required when push_to_github is True")
        
        # Create GitHub client
        client = GitHubClient(token=token, username=username)
        
        # Read the file content
        with open(static_json_path, "r") as f:
            content = f.read()
        
        # Push the file
        client.push_file(
            repo_owner=repo_owner,
            repo_name=repo_name,
            file_path="static.json",
            content=content,
            message=commit_message,
            branch=branch,
        )
        
        logger.info(f"Pushed static.json to {repo_owner}/{repo_name}")
    
    return static_json_path