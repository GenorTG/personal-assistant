"""Web search tool using DuckDuckGo."""
from typing import Dict, Any
import httpx
from ..base import BaseTool


class WebSearchTool(BaseTool):
    """Tool for searching the web."""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Search the internet for information using DuckDuckGo. Useful for finding current information, facts, or answers to questions."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    
    async def execute(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Execute web search.
        
        Args:
            query: Search query
            max_results: Maximum number of results
        
        Returns:
            Dictionary with search results
        """
        try:
            # Use DuckDuckGo instant answer API
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try instant answer first
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check for instant answer
                    if data.get("AbstractText"):
                        return {
                            "result": {
                                "type": "instant_answer",
                                "answer": data.get("AbstractText"),
                                "source": data.get("AbstractURL", ""),
                                "query": query
                            }
                        }
                    
                    # Fallback to web results
                    # Note: DuckDuckGo doesn't provide a public search API
                    # In production, you might want to use a different service
                    return {
                        "result": {
                            "type": "search",
                            "query": query,
                            "message": "Web search completed. For detailed results, consider using a search API service.",
                            "suggestion": "Try rephrasing your query or use more specific terms."
                        }
                    }
                else:
                    return {
                        "error": f"Search API returned status {response.status_code}"
                    }
        except Exception as e:
            return {
                "error": f"Error performing web search: {str(e)}"
            }

