"""Chat conversation manager."""
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
import json
import logging
from ..memory.store import MemoryStore
from ..tools.manager import ToolManager
from .message_builder import MessageBuilder
from ...utils.helpers import generate_conversation_id, get_timestamp
from ...config.settings import settings

logger = logging.getLogger(__name__)


class ChatManager:
    """Manages chat conversations and message flow."""
    
    def __init__(
        self,
        service_manager: Any,  # ServiceManager instance
        memory_store: MemoryStore,
        tool_manager: Optional[ToolManager] = None
    ):
        logger.info("      Setting up ChatManager...")
        self.service_manager = service_manager
        self.memory_store = memory_store
        self.tool_manager = tool_manager
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._conversation_names: Dict[str, str] = {}
        self._initialized = False
        logger.info("      ChatManager setup complete (conversations load on first use)")
    
    async def _initialize(self):
        """Initialize by loading conversations from persistent storage."""
        if self._initialized:
            return
        
        # Load conversations from memory store
        stored_conversations = await self.memory_store.list_conversations()
        for conv_data in stored_conversations:
            conv_id = conv_data["conversation_id"]
            # Load messages
            messages = await self.memory_store.get_conversation(conv_id)
            # None means conversation doesn't exist (404), skip it
            if messages is None:
                logger.warning(f"Conversation {conv_id} listed but not found, skipping")
                continue
            # Empty list means conversation exists but has no messages
            if messages:
                self.conversations[conv_id] = messages
            else:
                self.conversations[conv_id] = []
            
            # Store name if available
            if conv_data.get("name"):
                self._conversation_names[conv_id] = conv_data["name"]
        
        self._initialized = True
    
    async def _generate_conversation_name(self, conversation_id: str) -> str:
        """Generate a default name for a conversation like 'Chat 1', 'Chat 2', etc."""
        await self._initialize()
        
        # Count existing conversations to determine next number
        all_conversations = await self.memory_store.list_conversations()
        existing_count = len(all_conversations)
        
        # Find the next available number
        used_numbers = set()
        for conv in all_conversations:
            name = conv.get("name", "")
            if name and name.startswith("Chat "):
                try:
                    num = int(name.replace("Chat ", ""))
                    used_numbers.add(num)
                except ValueError:
                    pass
        
        # Find first unused number
        next_num = 1
        while next_num in used_numbers:
            next_num += 1
        
        name = f"Chat {next_num}"
        self._conversation_names[conversation_id] = name
        await self.memory_store.set_conversation_name(conversation_id, name)
        return name
    
    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        sampler_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a user message and generate response."""
        await self._initialize()
        
        # Generate conversation ID if new
        if not conversation_id:
            conversation_id = generate_conversation_id()
            self.conversations[conversation_id] = []
            # Generate default name
            await self._generate_conversation_name(conversation_id)
        
        # Validate message
        if not message or not isinstance(message, str) or len(message.strip()) == 0:
            raise ValueError("Message must be a non-empty string")
        
        # Store user message
        user_msg = {
            "role": "user",
            "content": message,
            "timestamp": get_timestamp()
        }
        self.conversations[conversation_id].append(user_msg)
        
        # Retrieve relevant context from memory (exclude current conversation)
        context = await self.memory_store.retrieve_context(
            query=message,
            exclude_conversation_id=conversation_id,
            conversation_id=conversation_id
        )
        
        # Validate context format
        if context is not None:
            if not isinstance(context, dict):
                logger.warning("Context is not a dict, ignoring: %s", type(context))
                context = None
            elif "retrieved_messages" in context and not isinstance(context["retrieved_messages"], list):
                logger.warning("Context 'retrieved_messages' is not a list, ignoring")
                context = {"retrieved_messages": []}
        
        # Get conversation history
        history = self.conversations[conversation_id]
        
        # Validate history format
        if not isinstance(history, list):
            logger.error("History is not a list: %s", type(history))
            history = []
        else:
            # Ensure all messages have required fields
            for i, msg in enumerate(history):
                if not isinstance(msg, dict):
                    logger.warning("Message %d is not a dict, skipping: %s", i, msg)
                    continue
                if 'role' not in msg or 'content' not in msg:
                    logger.warning("Message %d missing 'role' or 'content', fixing", i)
                    msg.setdefault('role', 'user')
                    msg.setdefault('content', '')
        
        # Get LLM settings
        llm_manager = self.service_manager.llm_manager
        
        # Update sampler settings if provided
        if sampler_params:
            llm_manager.update_settings(sampler_params)
        
        # Call LLM manager directly (merged from LLM service, no HTTP)
        try:
            # Check if model is loaded
            if not llm_manager.is_model_loaded():
                raise RuntimeError("No model loaded. Please load a model first.")
            
            # Prepare tool results (empty for initial call)
            tool_results = None
            
            # Call LLM manager's generate_response directly
            # It expects: message (str), history (List[Dict]), context (Dict), tool_results (List[Dict])
            # Let the LLM decide whether to use tools - no forced detection
            response = await llm_manager.generate_response(
                message=message,
                history=history,
                context=context,
                tool_results=tool_results,
                stream=False
            )
            
            # Validate response
            if response is None:
                raise RuntimeError("LLM generate_response returned None")
            if not isinstance(response, dict):
                raise RuntimeError(f"LLM generate_response returned invalid type: {type(response)}")
            
            assistant_content = response.get("response", "")
            tool_calls_data = response.get("tool_calls", [])
            
            logger.info(f"[CHAT MANAGER] LLM response received - content length: {len(assistant_content)}, tool_calls: {len(tool_calls_data) if tool_calls_data else 0}")
            
            # Parse tool calls from OpenAI format
            parsed_tool_calls = []
            if tool_calls_data:
                logger.info(f"[CHAT MANAGER] ✅ Tool calls received from LLM manager: {len(tool_calls_data)}")
                for tc in tool_calls_data:
                    try:
                        # OpenAI format: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
                        function_data = tc.get("function", {})
                        arguments_str = function_data.get("arguments", "{}")
                        # Arguments come as JSON string from OpenAI
                        try:
                            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                        except json.JSONDecodeError:
                            arguments = {}
                        
                        parsed_tool_calls.append({
                            "id": tc.get("id"),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": function_data.get("name"),
                                "arguments": arguments_str  # Keep as string for OpenAI format
                            }
                        })
                    except (KeyError, AttributeError) as e:
                        logger.warning(f"Failed to parse tool call: {e}")
                        continue
            
            logger.info(f"Parsed tool calls: {len(parsed_tool_calls)}")
            for i, tc in enumerate(parsed_tool_calls):
                logger.info(f"  Tool call {i+1}: {tc.get('function', {}).get('name')} (id: {tc.get('id')})")
            
            # Handle tool calls if present
            initial_content = assistant_content
            tool_execution_results = []  # Initialize to avoid UnboundLocalError
            
            if parsed_tool_calls and self.tool_manager:
                logger.info(f"[CHAT MANAGER] 🔧 Executing {len(parsed_tool_calls)} tool call(s)...")
                for i, tc in enumerate(parsed_tool_calls):
                    args_str = tc.get('function', {}).get('arguments', '{}')
                    try:
                        args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
                        logger.info(f"[CHAT MANAGER]   Tool call {i+1}: {tc.get('function', {}).get('name', 'unknown')}")
                        logger.info(f"[CHAT MANAGER]     Arguments (raw): {args_str}")
                        logger.info(f"[CHAT MANAGER]     Arguments (parsed): {json.dumps(args_dict, indent=6)}")
                    except:
                        logger.info(f"[CHAT MANAGER]   Tool call {i+1}: {tc.get('function', {}).get('name', 'unknown')} with args: {args_str}")
                # Execute tools
                logger.info(f"[CHAT MANAGER] Calling tool_manager.execute_tools with {len(parsed_tool_calls)} tool call(s)")
                tool_execution_results = await self.tool_manager.execute_tools(
                    tool_calls=parsed_tool_calls,
                    conversation_id=conversation_id
                )
                
                logger.info(f"[CHAT MANAGER] ✅ Tool execution completed - received {len(tool_execution_results) if tool_execution_results else 0} result(s)")
                if tool_execution_results:
                    for i, result in enumerate(tool_execution_results):
                        logger.info(f"[CHAT MANAGER]   Result {i+1}: {result.get('name')} - success={result.get('success')}, error={result.get('error')}")
            elif parsed_tool_calls and not self.tool_manager:
                logger.warning(f"[CHAT MANAGER] ⚠️  Tool calls detected but tool_manager is not available!")
                tool_execution_results = []  # Ensure it's initialized
            else:
                # No tool calls
                logger.info(f"[CHAT MANAGER] No tool calls in response")
                tool_execution_results = []  # Ensure it's initialized
            
            # Validate tool execution results (only if we have tool calls and results)
            if parsed_tool_calls:
                if tool_execution_results is None:
                    logger.warning("tool_manager.execute_tools returned None, skipping tool results")
                    tool_execution_results = []
                if not isinstance(tool_execution_results, list):
                    logger.warning(f"tool_manager.execute_tools returned invalid type: {type(tool_execution_results)}, skipping tool results")
                    tool_execution_results = []
                
                # Format tool results for LLM
                tool_results = []
                for i, res in enumerate(tool_execution_results):
                    if res is None:
                        logger.warning(f"Skipping None result at index {i} in tool_execution_results")
                        continue
                    if not isinstance(res, dict):
                        logger.warning(f"Skipping invalid result type at index {i}: {type(res)}")
                        continue
                    
                    tool_name = res.get("name", "unknown")
                    success = res.get("success", False)
                    error = res.get("error")
                    result_data = res.get("result")
                    
                    logger.info(f"  Tool result {i+1} ({tool_name}): success={success}, error={error is not None}")
                    if error:
                        logger.warning(f"    Error: {error}")
                    if result_data:
                        logger.debug(f"    Result: {str(result_data)[:200]}...")
                    
                    tool_results.append({
                        "id": res.get("id"),
                        "name": tool_name,
                        "result": result_data if success else f"Error: {error}",
                        "success": success,
                        "error": error,
                        "arguments": res.get("arguments", {})  # Include original arguments
                    })
                
                logger.info(f"Formatted {len(tool_results)} tool result(s) for LLM follow-up")
                
                # CRITICAL: Before making follow-up call, we need to add the assistant message with tool_calls to history
                # This ensures the history is correct for the follow-up call
                assistant_msg_with_tool_calls = {
                    "role": "assistant",
                    "content": initial_content if initial_content else None,
                    "tool_calls": parsed_tool_calls,  # Store in OpenAI format
                    "timestamp": get_timestamp()
                }
                # Add to history temporarily for follow-up call
                history_with_tool_calls = history + [assistant_msg_with_tool_calls]
                
                # Make follow-up call with tool results
                logger.info("Making follow-up LLM call with tool results...")
                logger.debug(f"Follow-up history length: {len(history_with_tool_calls)}, last message role: {history_with_tool_calls[-1].get('role') if history_with_tool_calls else 'none'}")
                follow_up_response = None
                follow_up_content = ""
                try:
                    follow_up_response = await llm_manager.generate_response(
                        message=message,
                        history=history_with_tool_calls,
                        context=context,
                        tool_results=tool_results,
                        stream=False
                    )
                    logger.info(f"Follow-up response received: {follow_up_response is not None}")
                    
                    # Validate follow-up response
                    if follow_up_response is None:
                        logger.warning("Follow-up LLM generate_response returned None, generating fallback response")
                        raise Exception("Follow-up response is None")
                    elif not isinstance(follow_up_response, dict):
                        logger.warning(f"Follow-up LLM generate_response returned invalid type: {type(follow_up_response)}, generating fallback response")
                        raise Exception(f"Follow-up response is invalid type: {type(follow_up_response)}")
                    else:
                        follow_up_content = follow_up_response.get("response", "")
                        logger.info(f"Follow-up content length: {len(follow_up_content)}")
                        
                        # If follow-up content is empty, generate a fallback
                        if not follow_up_content:
                            raise Exception("Follow-up content is empty")
                except Exception as e:
                    logger.error(f"Follow-up LLM call failed: {e}", exc_info=True)
                    # Generate a simple response based on tool results
                    tool_names = [r.get("name", "tool") for r in tool_execution_results if r.get("success")]
                    if tool_names:
                        follow_up_content = f"I have successfully executed the {', '.join(tool_names)} tool(s)."
                    else:
                        follow_up_content = "I attempted to execute the requested tool(s)."
                
                # Combine initial content with follow-up
                if initial_content and follow_up_content:
                    assistant_content = f"{initial_content}\n\n{follow_up_content}".strip()
                elif follow_up_content:
                    assistant_content = follow_up_content
                elif initial_content:
                    assistant_content = initial_content
                else:
                    # Final fallback
                    tool_names = [r.get("name", "tool") for r in tool_execution_results if r.get("success")]
                    assistant_content = f"I have successfully executed the {', '.join(tool_names)} tool(s)." if tool_names else "Tool execution completed."
                
                # Format tool calls with execution results for frontend display
                tool_calls_with_results = []
                for i, tool_call in enumerate(parsed_tool_calls):
                    tool_result = tool_execution_results[i] if i < len(tool_execution_results) else None
                    function_data = tool_call.get("function", {})
                    # Parse arguments for display
                    arguments_str = function_data.get("arguments", "{}")
                    try:
                        arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    tool_calls_with_results.append({
                        "id": tool_call.get("id"),
                        "name": function_data.get("name"),
                        "arguments": arguments,
                        "success": tool_result.get("success", False) if tool_result else False,
                        "result": tool_result.get("result") if tool_result else None,
                        "error": tool_result.get("error") if tool_result else None
                    })
                
                # Store assistant response with tool calls in OpenAI format
                # CRITICAL: Store parsed_tool_calls (OpenAI format) not tool_calls_with_results (custom format)
                assistant_msg = {
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": parsed_tool_calls,  # Store in OpenAI format for history
                    "timestamp": get_timestamp()
                }
                self.conversations[conversation_id].append(assistant_msg)
                
                # Save to vector store and memory
                conv_name = self._conversation_names.get(conversation_id)
                await self.memory_store.store_conversation(
                    conversation_id=conversation_id,
                    messages=[user_msg, assistant_msg],
                    name=conv_name
                )
                
                return {
                    "response": assistant_content,
                    "conversation_id": conversation_id,
                    "context_used": context.get("retrieved_messages", []) if context else [],
                    "tool_calls": tool_calls_with_results
                }
            
            # No tool calls - store assistant response and return
            assistant_msg = {
                "role": "assistant",
                "content": assistant_content,
                "timestamp": get_timestamp()
            }
            self.conversations[conversation_id].append(assistant_msg)
            
            # Save to vector store and memory
            conv_name = self._conversation_names.get(conversation_id)
            await self.memory_store.store_conversation(
                conversation_id=conversation_id,
                messages=[user_msg, assistant_msg],
                name=conv_name
            )
            
            # Format tool calls for response (convert to simple format)
            formatted_tool_calls = []
            for tc in parsed_tool_calls:
                function_data = tc.get("function", {})
                arguments_str = function_data.get("arguments", "{}")
                try:
                    arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                except json.JSONDecodeError:
                    arguments = {}
                formatted_tool_calls.append({
                    "id": tc.get("id"),
                    "name": function_data.get("name"),
                    "arguments": arguments
                })
            
            return {
                "response": assistant_content,
                "conversation_id": conversation_id,
                "context_used": context.get("retrieved_messages", []) if context else [],
                "tool_calls": formatted_tool_calls
            }
        except RuntimeError as e:
            logger.error(f"LLM error: {e}")
            raise RuntimeError("LLM service not available. Please ensure the LLM service is running.") from e
        except httpx.TimeoutException as e:
            logger.error(f"LLM request timed out: {e}")
            raise RuntimeError("LLM request timed out. The model may be processing a large request.") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM service returned error status {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"LLM service error: {e.response.status_code} - {e.response.text}") from e
        except Exception as e:
            logger.error(f"Error calling LLM service: {e}", exc_info=True)
            raise RuntimeError(f"LLM request failed: {str(e)}") from e
    
    
    async def get_conversation(self, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get conversation by ID."""
        await self._initialize()
        
        # Try to load from memory if not in cache
        if conversation_id not in self.conversations:
            messages = await self.memory_store.get_conversation(conversation_id)
            if messages is not None:
                self.conversations[conversation_id] = messages
            else:
                return None
        
        return self.conversations.get(conversation_id)
    
    async def list_conversations(self) -> List[str]:
        """List all conversation IDs."""
        await self._initialize()
        return list(self.conversations.keys())

    async def set_conversation_name(self, conversation_id: str, name: str) -> bool:
        """Set the name of a conversation.
        
        Args:
            conversation_id: ID of the conversation
            name: New name for the conversation
            
        Returns:
            True if successful, False if conversation not found
        """
        await self._initialize()
        
        # Check if conversation exists
        if conversation_id not in self.conversations:
            # Try to load it
            messages = await self.memory_store.get_conversation(conversation_id)
            if messages is None:
                return False
            self.conversations[conversation_id] = messages
        
        # Update cache
        self._conversation_names[conversation_id] = name
        
        # Update in database
        try:
            await self.memory_store.set_conversation_name(conversation_id, name)
            return True
        except Exception as e:
            logger.error(f"Error setting conversation name: {e}", exc_info=True)
            return False
    
    async def get_conversation_name(self, conversation_id: str) -> Optional[str]:
        """Get the name of a conversation.
        
        OPTIMIZED: Loads single conversation instead of all conversations.
        """
        await self._initialize()
        if conversation_id in self._conversation_names:
            return self._conversation_names[conversation_id]
        
        # OPTIMIZATION: Load single conversation directly instead of loading all
        try:
            conv = await self.memory_store.get_conversation(conversation_id)
            if conv:
                name = conv.get("name")
                if name:
                    self._conversation_names[conversation_id] = name
                    return name
        except Exception as e:
            logger.warning(f"Error loading conversation {conversation_id} for name: {e}")
        
        return None

    async def create_conversation(self) -> str:
        """Create a new conversation.
        
        Returns:
            New conversation ID
        """
        await self._initialize()
        from ...utils.helpers import generate_conversation_id
        conversation_id = generate_conversation_id()
        self.conversations[conversation_id] = []
        # Generate default name
        name = await self._generate_conversation_name(conversation_id)
        # Persist empty conversation to database with name
        await self.memory_store.store_conversation(conversation_id, [], name=name)
        return conversation_id
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation.
        
        Args:
            conversation_id: ID of conversation to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self._initialize()
        
        # Delete from persistent storage
        success = await self.memory_store.delete_conversation(conversation_id)
        
        # Delete from memory cache
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        if conversation_id in self._conversation_names:
            del self._conversation_names[conversation_id]
        
        return success
    
    async def get_conversation_count(self) -> int:
        """Get total number of conversations."""
        await self._initialize()
        return len(self.conversations)