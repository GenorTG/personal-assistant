"use client";

import { useState, useEffect, useCallback } from "react";
import { Settings, Package, Bug } from "lucide-react";
import { api } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import SettingsPanel from "@/components/SettingsPanel";
import ModelBrowser from "@/components/ModelBrowser";
import DebugPanel from "@/components/DebugPanel";
import ConversationTabs from "@/components/ConversationTabs";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ServiceStatusProvider } from "@/contexts/ServiceStatusContext";
import { useSettings } from "@/contexts/SettingsContext";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { useToast } from "@/contexts/ToastContext";

export default function Home() {
  const { modelLoaded, currentModel, refresh: refreshSettings } = useSettings();
  const { showError, showConfirm } = useToast();
  const { isReady: backendReady, error: backendError, checkHealth: checkBackend } = useBackendHealth({
    interval: 5000, // Check every 5 seconds for faster updates
    enabled: true,
  });
  const [showSettings, setShowSettings] = useState(false);
  const [showModelBrowser, setShowModelBrowser] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(384); // Default 384px (w-96)
  const [conversations, setConversations] = useState<any[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<
    string | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadConversations = useCallback(async (forceRefresh: boolean = false) => {
    try {
      setError(null);
      
      // Check cache first (unless force refresh) - OPTIMISTIC LOADING
      let cachedConvs: any[] | null = null;
      if (!forceRefresh) {
        const cached = localStorage.getItem('conversations_cache');
        const cacheTime = localStorage.getItem('conversations_cache_time');
        if (cached && cacheTime) {
          const age = Date.now() - parseInt(cacheTime, 10);
          // Use cache if less than 30 seconds old
          if (age < 30000) {
            try {
              cachedConvs = JSON.parse(cached);
              if (cachedConvs && Array.isArray(cachedConvs)) {
                console.log(`[Conversations] Loaded ${cachedConvs.length} conversations from cache`);
                // Show cached data immediately
                setConversations(cachedConvs);
                setLoading(false);
              }
            } catch {
              // Cache corrupted, continue to fetch
            }
          }
        }
      }
      
      // Try to fetch fresh data in background (non-blocking)
      try {
        const convs = (await api.getConversations()) as any[];
        console.log(`[Conversations] Loaded ${convs.length} conversations from backend`);
        setConversations(convs);
        
        // Cache the result
        localStorage.setItem('conversations_cache', JSON.stringify(convs));
        localStorage.setItem('conversations_cache_time', Date.now().toString());
        
        return convs;
      } catch (fetchError) {
        // If we have cached data, use it and don't show error
        if (cachedConvs && cachedConvs.length > 0) {
          console.warn("[Conversations] Backend fetch failed, using cached data:", fetchError);
          return cachedConvs;
        }
        // No cached data, show error
        throw fetchError;
      }
    } catch (error) {
      console.error("Error loading conversations:", error);
      // Only set error if we don't have cached data
      const cached = localStorage.getItem('conversations_cache');
      if (!cached) {
        setError(
          error instanceof Error ? error.message : "Failed to load conversations"
        );
        setConversations([]);
      }
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const handleNewConversation = useCallback(async () => {
    try {
      const response = (await api.createConversation()) as any;
      if (!response || !response.conversation_id) {
        throw new Error("Invalid response from server");
      }
      
      const newId = response.conversation_id;
      setCurrentConversationId(newId);
      localStorage.setItem("lastConversationId", newId);
      
      // Reload conversations to include the new one (force refresh)
      await loadConversations(true);
      
      // Ensure the new conversation is selected
      setCurrentConversationId(newId);
    } catch (error) {
      console.error("Error creating conversation:", error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      showError(`Error creating conversation: ${errorMessage}`);
      
      // Try to reload conversations anyway in case it was partially created
      await loadConversations(true);
    }
  }, [loadConversations, showError]);

  const initializeApp = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      // NO BLOCKING WAIT - Load cached data immediately, fetch fresh data in background
      console.log("[App] Initializing app with optimistic loading...");

      // Sync the health hook state with API client state (non-blocking)
      checkBackend();

      // Load conversations immediately (will use cache if available)
      const convs = await loadConversations();

      // Try to refresh settings in background (non-blocking, won't block UI)
      refreshSettings().catch(err => {
        console.warn("[App] Settings refresh failed (non-critical):", err);
      });

      console.log(`[App] Loaded ${convs.length} conversations`);

      // If no conversations exist, try to create a default one (only if backend is ready)
      if (convs.length === 0) {
        // Check if backend is ready before creating conversation
        const isReady = await api.checkBackendHealth();
        if (isReady) {
          console.log("[App] No conversations found, creating new one...");
          handleNewConversation().catch(err => {
            console.warn("[App] Failed to create default conversation:", err);
          });
        } else {
          console.log("[App] Backend not ready, will create conversation when ready");
        }
      } else {
        // Try to load last opened conversation from localStorage
        const lastConversationId = localStorage.getItem("lastConversationId");
        const lastConversationExists = lastConversationId && 
          convs.some((c: any) => c.conversation_id === lastConversationId);
        
        if (lastConversationExists) {
          console.log(`[App] Restoring last conversation: ${lastConversationId}`);
          setCurrentConversationId(lastConversationId);
        } else {
          // Clear invalid localStorage entry
          if (lastConversationId) {
            localStorage.removeItem("lastConversationId");
          }
          // Default to most recent conversation
          const firstConversationId = convs[0]?.conversation_id;
          if (firstConversationId) {
            console.log(`[App] Setting current conversation to: ${firstConversationId}`);
            setCurrentConversationId(firstConversationId);
            localStorage.setItem("lastConversationId", firstConversationId);
          }
        }
      }
    } catch (error) {
      console.error("[App] Error initializing app:", error);
      // Don't show error if we have cached conversations
      const cached = localStorage.getItem('conversations_cache');
      if (!cached) {
        setError(
          error instanceof Error ? error.message : "Failed to initialize app"
        );
      }
      setLoading(false);
    }
  }, [refreshSettings, loadConversations, handleNewConversation, checkBackend]);

  // Only run initializeApp once on mount
  useEffect(() => {
    initializeApp();
    // Settings are now managed by SettingsContext and auto-refresh every 30s
    // No need for separate model status polling
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps - only run on mount

  // Check backend health immediately on mount for faster status update
  // Note: useBackendHealth hook already handles initial check, this is just for immediate sync
  useEffect(() => {
    checkBackend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  // Backend health is now managed by useBackendHealth hook
  useEffect(() => {
    if (backendError && !error) {
      setError(backendError);
    } else if (backendReady && error?.includes("Backend is not responding")) {
      setError(null);
    }
  }, [backendError, backendReady, error]);

  // Model status is now managed by SettingsContext
  // No need for separate loadModelStatus function

  const handleDeleteConversation = async (id: string) => {
    showConfirm(
      "Are you sure you want to delete this conversation?",
      async () => {
        try {
          await api.deleteConversation(id);

          // Clear localStorage if deleting the last opened conversation
          if (localStorage.getItem("lastConversationId") === id) {
            localStorage.removeItem("lastConversationId");
          }

          // Update current conversation before reloading
          if (currentConversationId === id) {
            const remaining = conversations.filter((c) => c.conversation_id !== id);
            const nextId =
              remaining.length > 0 ? remaining[0].conversation_id : null;
            setCurrentConversationId(nextId);
            if (nextId) {
              localStorage.setItem("lastConversationId", nextId);
            } else {
              // No conversations left, create a new one
              await handleNewConversation();
              return; // handleNewConversation already calls loadConversations
            }
          }
          
          // Reload conversations list to reflect deletion
          await loadConversations();
        } catch (error) {
          console.error("Error deleting conversation:", error);
          const errorMessage = error instanceof Error ? error.message : "Unknown error";
          showError(`Error deleting conversation: ${errorMessage}`);
          
          // Still reload conversations in case the deletion partially succeeded
          await loadConversations();
        }
      }
    );
  };

  const handleSwitchConversation = (id: string) => {
    setCurrentConversationId(id);
    localStorage.setItem("lastConversationId", id);
  };

  const handleRenameConversation = async (id: string, newName: string) => {
    if (!newName || !newName.trim()) {
      showError("Conversation name cannot be empty");
      return;
    }

    try {
      await api.renameConversation(id, newName.trim());
      
      // Clear cache and reload conversations to reflect the change
      localStorage.removeItem('conversations_cache');
      await loadConversations(true);
    } catch (error) {
      console.error('Error renaming conversation:', error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      showError(`Error renaming conversation: ${errorMessage}`);
      
      // Reload conversations to get current state (rename may have partially succeeded)
      await loadConversations();
    }
  };

  const handlePinConversation = async (id: string, pinned: boolean) => {
    try {
      await api.pinConversation(id, pinned);
      
      // Clear cache and reload conversations to reflect the change
      localStorage.removeItem('conversations_cache');
      await loadConversations(true);
    } catch (error) {
      console.error('Error pinning conversation:', error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      showError(`Error ${pinned ? 'pinning' : 'unpinning'} conversation: ${errorMessage}`);
      
      // Reload conversations to get current state
      await loadConversations();
    }
  };

  const handleDeleteAllConversations = async () => {
    const pinnedCount = conversations.filter(c => c.pinned).length;
    const unpinnedCount = conversations.length - pinnedCount;
    
    let confirmMessage = `Are you sure you want to delete all ${unpinnedCount} unpinned conversation${unpinnedCount !== 1 ? 's' : ''}?`;
    if (pinnedCount > 0) {
      confirmMessage += `\n\nNote: ${pinnedCount} pinned conversation${pinnedCount !== 1 ? 's' : ''} will be preserved.`;
    }
    confirmMessage += '\n\nThis action cannot be undone.';
    
    showConfirm(confirmMessage, async () => {
      try {
        await api.deleteAllConversations();
        
        // Clear localStorage cache
        localStorage.removeItem("lastConversationId");
        localStorage.removeItem("conversations_cache");
        localStorage.removeItem("conversations_cache_time");
        
        // Force reload conversations to get updated list from backend (bypass cache)
        const updatedConversations = await loadConversations(true);
        
        // Clear current conversation ID
        setCurrentConversationId(null);
        
        // Check if any conversations remain after deletion
        if (!updatedConversations || updatedConversations.length === 0) {
          // All conversations deleted - create a new default one
          await handleNewConversation();
        } else {
          // Select the first remaining conversation (should be pinned ones)
          setCurrentConversationId(updatedConversations[0].id);
        }
      } catch (error) {
        console.error("Error deleting all conversations:", error);
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        showError(`Error deleting all conversations: ${errorMessage}`);
        
        // Reload conversations to get current state
        await loadConversations(true);
      }
    });
  };

  const handleConversationNotFound = (conversationId: string) => {
    // Conversation not found, will be removed from list
    
    // Remove from conversations list and get remaining conversations
    let remaining: any[] = [];
    setConversations((prev) => {
      remaining = prev.filter((c) => c.conversation_id !== conversationId);
      return remaining;
    });
    
    // If this was the current conversation, switch to another one
    if (currentConversationId === conversationId) {
      if (remaining.length > 0) {
        setCurrentConversationId(remaining[0].conversation_id);
        localStorage.setItem("lastConversationId", remaining[0].conversation_id);
      } else {
        // No conversations left, create a new one
        handleNewConversation();
      }
    }
    
    // Clear from localStorage if it was the last opened
    if (localStorage.getItem("lastConversationId") === conversationId) {
      localStorage.removeItem("lastConversationId");
    }
  };

  return (
    <ServiceStatusProvider>
      <ErrorBoundary>
        <div className="min-h-screen flex flex-col">
          {/* Header */}
          <header className="bg-gradient-to-r from-primary-600 to-purple-600 text-white shadow-lg">
            <div className="container mx-auto px-4 py-4">
              <div className="flex justify-between items-center">
                <h1 className="text-2xl font-bold">Personal AI Assistant</h1>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (showModelBrowser) {
                        setShowModelBrowser(false);
                      } else {
                        setShowModelBrowser(true);
                        setShowSettings(false);
                        setShowDebug(false);
                      }
                    }}
                    className={`btn-icon ${
                      showModelBrowser ? "bg-white/30" : ""
                    }`}
                    title="Model Browser"
                  >
                    <Package size={20} />
                  </button>
                  <button
                    onClick={() => {
                      if (showSettings) {
                        setShowSettings(false);
                      } else {
                        setShowSettings(true);
                        setShowModelBrowser(false);
                        setShowDebug(false);
                      }
                    }}
                    className={`btn-icon ${showSettings ? "bg-white/30" : ""}`}
                    title="Settings"
                  >
                    <Settings size={20} />
                  </button>
                  <button
                    onClick={() => {
                      if (showDebug) {
                        setShowDebug(false);
                      } else {
                        setShowDebug(true);
                        setShowSettings(false);
                        setShowModelBrowser(false);
                      }
                    }}
                    className={`btn-icon ${showDebug ? "bg-white/30" : ""}`}
                    title="Debug Panel"
                  >
                    <Bug size={20} />
                  </button>
                </div>
              </div>
              {/* Model Status Bar */}
              <div className="mt-2 px-4 py-2 bg-white/10 rounded-lg">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Model Status:</span>
                  {modelLoaded && currentModel ? (
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                      <span className="truncate max-w-xs" title={currentModel}>
                        {currentModel.split(/[/\\]/).pop()}
                      </span>
                    </div>
                  ) : (
                    <span className="text-yellow-200">No model loaded</span>
                  )}
                </div>
              </div>
            </div>
          </header>

          {/* Backend Status */}
          {!backendReady && (
            <div className="w-full bg-yellow-50 border-b border-yellow-200 px-4 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></span>
                <p className="text-yellow-800">
                  Waiting for backend to be ready...
                </p>
              </div>
            </div>
          )}

          {/* Conversation Tabs */}
          {loading ? (
            <div className="w-full bg-gray-100 border-b border-gray-200 px-4 py-2 flex items-center justify-center">
              <p className="text-gray-600">Loading conversations...</p>
            </div>
          ) : error ? (
            <div className="w-full bg-red-50 border-b border-red-200 px-4 py-2 flex items-center justify-between">
              <p className="text-red-600">{error}</p>
              <button
                onClick={() => {
                  setError(null);
                  loadConversations(true);
                }}
                className="btn-secondary text-sm"
              >
                Retry
              </button>
            </div>
          ) : (
            <ConversationTabs
              conversations={conversations}
              currentId={currentConversationId}
              onNew={handleNewConversation}
              onSwitch={handleSwitchConversation}
              onDelete={handleDeleteConversation}
              onDeleteAll={handleDeleteAllConversations}
              onRename={handleRenameConversation}
              onPin={handlePinConversation}
            />
          )}

          {/* Main Content */}
          <div className="flex-1 flex overflow-hidden relative">
            {/* Chat Panel */}
            <div
              className="flex-1 flex flex-col transition-all duration-300"
              style={{
                marginRight: showSettings || showModelBrowser || showDebug ? `${sidebarWidth}px` : '0',
              }}
            >
              <ChatPanel 
                conversationId={currentConversationId} 
                onConversationNotFound={handleConversationNotFound}
                onConversationCreated={async (newId) => {
                  setCurrentConversationId(newId);
                  localStorage.setItem("lastConversationId", newId);
                  await loadConversations(true);
                }}
              />
            </div>

            {/* Side Panels - Only show one at a time */}
            {showSettings && !showModelBrowser && !showDebug && (
              <SettingsPanel 
                onClose={() => setShowSettings(false)}
                onWidthChange={setSidebarWidth}
              />
            )}
            {showModelBrowser && !showSettings && !showDebug && (
              <ModelBrowser onClose={() => setShowModelBrowser(false)} />
            )}
            {showDebug && !showSettings && !showModelBrowser && (
              <DebugPanel 
                onClose={() => setShowDebug(false)}
                onWidthChange={setSidebarWidth}
              />
            )}
          </div>
        </div>
      </ErrorBoundary>
    </ServiceStatusProvider>
  );
}
