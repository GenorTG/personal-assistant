"""Google search tool for web search and aggregated results."""
from typing import Dict, Any, List
import httpx
import logging
from ..base_tool import BaseTool

logger = logging.getLogger(__name__)


class GoogleSearchTool(BaseTool):
    """Tool for performing web searches and aggregating results."""
    
    @property
    def name(self) -> str:
        return "google_search"
    
    @property
    def description(self) -> str:
        return """Search the web for current information, facts, or data. Use this tool when:
- The user asks about current events, news, or recent information
- You need factual information that may have changed or that you're not certain about
- The user asks "what is X" or "tell me about X" and you need up-to-date information
- You need to verify information or find specific data online

Provide a clear search query that captures what the user is looking for."""
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string. Extract the main topic or question from the user's message. Make it clear and specific. Examples: 'current weather in New York', 'latest news about AI', 'how to bake a cake'"
                },
                "num_results": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Number of search results to return (1-10)"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Google search tool.
        
        Uses DuckDuckGo as a free alternative to Google Search API.
        """
        query = arguments.get("query", "")
        num_results = arguments.get("num_results", 5)
        
        if not query:
            return {
                "error": "Query is required",
                "results": []
            }
        
        try:
            # Use DuckDuckGo Instant Answer API and HTML search as fallback
            # DuckDuckGo provides free search without API keys
            results = await self._search_duckduckgo(query, num_results)
            
            return {
                "query": query,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            logger.error(f"Error performing search: {e}", exc_info=True)
            return {
                "error": f"Search failed: {str(e)}",
                "results": []
            }
    
    async def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo.
        
        Uses DuckDuckGo's HTML search endpoint and parses results.
        """
        try:
            # Try DuckDuckGo Instant Answer API first (for structured data)
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try instant answer API
                instant_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
                try:
                    response = await client.get(instant_url)
                    if response.status_code == 200:
                        data = response.json()
                        
                        results = []
                        
                        # Add abstract if available
                        if data.get("AbstractText"):
                            results.append({
                                "title": data.get("Heading", query),
                                "url": data.get("AbstractURL", ""),
                                "snippet": data.get("AbstractText", ""),
                                "source": "DuckDuckGo Instant Answer"
                            })
                        
                        # Add related topics
                        for topic in data.get("RelatedTopics", [])[:num_results - len(results)]:
                            if isinstance(topic, dict) and "Text" in topic:
                                results.append({
                                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                                    "url": topic.get("FirstURL", ""),
                                    "snippet": topic.get("Text", ""),
                                    "source": "DuckDuckGo Related Topics"
                                })
                        
                        if results:
                            return results[:num_results]
                except Exception as e:
                    logger.debug(f"DuckDuckGo instant answer API failed: {e}")
                
                # Fallback: Use DuckDuckGo HTML search (simpler, more reliable)
                # We'll use a simple approach: search and extract basic info
                search_url = f"https://html.duckduckgo.com/html/?q={query}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                response = await client.get(search_url, headers=headers, follow_redirects=True)
                
                if response.status_code == 200:
                    # Parse HTML results (simplified - just extract titles and URLs)
                    # For a production system, you'd want to use BeautifulSoup or similar
                    html = response.text
                    results = self._parse_duckduckgo_html(html, num_results)
                    
                    if results:
                        return results
                
                # If all else fails, return a message suggesting manual search
                return [{
                    "title": "Search Unavailable",
                    "url": f"https://duckduckgo.com/?q={query}",
                    "snippet": f"Unable to fetch search results automatically. Please search manually: {query}",
                    "source": "Fallback"
                }]
        except Exception as e:
            logger.error(f"Error in DuckDuckGo search: {e}", exc_info=True)
            raise
    
    def _parse_duckduckgo_html(self, html: str, num_results: int) -> List[Dict[str, Any]]:
        """Parse DuckDuckGo HTML search results.
        
        This is a simplified parser. For production, consider using BeautifulSoup.
        """
        results = []
        
        # Simple regex-based parsing (basic implementation)
        import re
        
        # Look for result links (DuckDuckGo HTML structure)
        # Pattern: <a class="result__a" href="...">Title</a>
        link_pattern = r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
        snippet_pattern = r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>([^<]+)</a>'
        
        links = re.findall(link_pattern, html)
        snippets = re.findall(snippet_pattern, html)
        
        for i, (url, title) in enumerate(links[:num_results]):
            snippet = snippets[i] if i < len(snippets) else ""
            results.append({
                "title": title.strip(),
                "url": url,
                "snippet": snippet.strip(),
                "source": "DuckDuckGo"
            })
        
        return results

