"use client";

import { useState, useEffect } from "react";
import { Settings, Package, Bug } from "lucide-react";
import { api } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import SettingsPanel from "@/components/SettingsPanel";
import ModelBrowser from "@/components/ModelBrowser";
import DebugPanel from "@/components/DebugPanel";
import ConversationTabs from "@/components/ConversationTabs";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ServiceStatusProvider } from "@/contexts/ServiceStatusContext";

export default function Home() {
  const [showSettings, setShowSettings] = useState(false);
  const [showModelBrowser, setShowModelBrowser] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<
    string | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [backendReady, setBackendReady] = useState(false);

  useEffect(() => {
    initializeApp();
    // Poll for model status every 10 seconds (reduced from 3s)
    const interval = setInterval(loadModelStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Check backend health periodically, but less frequently to avoid spam
    const checkBackend = async () => {
      try {
        const ready = await api.checkBackendHealth();
        setBackendReady(ready);
        // Only show error if backend was ready before and now it's not
        // This prevents false alarms during long operations
        if (!ready && backendReady && !error) {
          // Wait a bit before showing error - might just be a long operation
          setTimeout(() => {
            api.checkBackendHealth().then((stillDead) => {
              if (!stillDead) {
                setError(
                  "Backend is not responding. Please ensure the backend server is running."
                );
              }
            });
          }, 5000);
        } else if (ready && error?.includes("Backend is not responding")) {
          setError(null);
        }
      } catch {
        // Don't immediately mark as dead on exception
        // Might just be a timeout during long operation
      }
    };

    checkBackend();
    // Check every 30 seconds (reduced from 10s to minimize spam)
    const healthInterval = setInterval(checkBackend, 30000);
    return () => clearInterval(healthInterval);
  }, [error, backendReady]);

  const initializeApp = async () => {
    // Wait for backend to be ready first
    console.log("[App] Waiting for backend to be ready...");
    const ready = await api.waitForBackend(60000); // Wait up to 60 seconds
    if (!ready) {
      setError(
        "Backend is not responding. Please ensure the backend server is running on http://localhost:8000"
      );
      setLoading(false);
      return;
    }

    console.log("[App] Backend is ready, loading data...");
    await loadModelStatus();
    const convs = await loadConversations();

    // If no conversations exist, create a default one
    if (convs.length === 0) {
      await handleNewConversation();
    } else {
      // Try to load last opened conversation from localStorage
      const lastConversationId = localStorage.getItem("lastConversationId");
      if (
        lastConversationId &&
        convs.some((c) => c.conversation_id === lastConversationId)
      ) {
        setCurrentConversationId(lastConversationId);
      } else {
        // Default to most recent conversation
        setCurrentConversationId(convs[0].conversation_id);
        localStorage.setItem("lastConversationId", convs[0].conversation_id);
      }
    }
  };

  const loadModelStatus = async () => {
    try {
      // Check if backend is ready first
      const ready = await api.checkBackendHealth();
      if (!ready) {
        return; // Backend not ready, skip this attempt
      }
      const settings = (await api.getSettings()) as any;
      setModelLoaded(settings?.model_loaded || false);
      setCurrentModel(settings?.current_model || null);
    } catch (error) {
      // Only log if it's not a "backend not ready" error
      if (
        error instanceof Error &&
        !error.message.includes("Backend is not responding")
      ) {
        console.error("Error loading model status:", error);
      }
    }
  };

  const loadConversations = async () => {
    try {
      setError(null);
      const convs = (await api.getConversations()) as any[];
      console.log("Loaded conversations:", convs);
      setConversations(convs);
      return convs;
    } catch (error) {
      console.error("Error loading conversations:", error);
      setError(
        error instanceof Error ? error.message : "Failed to load conversations"
      );
      return [];
    } finally {
      setLoading(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const response = (await api.createConversation()) as any;
      const newId = response.conversation_id;
      setCurrentConversationId(newId);
      localStorage.setItem("lastConversationId", newId);
      await loadConversations();
    } catch (error) {
      console.error("Error creating conversation:", error);
      alert(
        `Error: ${error instanceof Error ? error.message : "Unknown error"}`
      );
    }
  };

  const handleDeleteConversation = async (id: string) => {
    if (!confirm("Are you sure you want to delete this conversation?")) {
      return;
    }

    try {
      await api.deleteConversation(id);

      // Clear localStorage if deleting the last opened conversation
      if (localStorage.getItem("lastConversationId") === id) {
        localStorage.removeItem("lastConversationId");
      }

      if (currentConversationId === id) {
        const remaining = conversations.filter((c) => c.conversation_id !== id);
        const nextId =
          remaining.length > 0 ? remaining[0].conversation_id : null;
        setCurrentConversationId(nextId);
        if (nextId) {
          localStorage.setItem("lastConversationId", nextId);
        }
      }
      await loadConversations();
    } catch (error) {
      console.error("Error deleting conversation:", error);
      alert(
        `Error: ${error instanceof Error ? error.message : "Unknown error"}`
      );
    }
  };

  const handleSwitchConversation = (id: string) => {
    setCurrentConversationId(id);
    localStorage.setItem("lastConversationId", id);
  };

  const handleRenameConversation = async (id: string, newName: string) => {
    try {
      // Call backend API to rename conversation
      await fetch(`http://localhost:8000/api/conversations/${id}/rename`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newName }),
      });
      
      // Reload conversations to reflect the change
      await loadConversations();
    } catch (error) {
      console.error('Error renaming conversation:', error);
      alert(
        `Error: ${error instanceof Error ? error.message : "Unknown error"}`
      );
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
                  loadConversations();
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
              onRename={handleRenameConversation}
            />
          )}

          {/* Main Content */}
          <div className="flex-1 flex overflow-hidden relative">
            {/* Chat Panel */}
            <div
              className={`flex-1 flex flex-col transition-all duration-300 ${
                showSettings || showModelBrowser || showDebug ? "mr-96" : ""
              }`}
            >
              <ChatPanel conversationId={currentConversationId} />
            </div>

            {/* Side Panels - Only show one at a time */}
            {showSettings && !showModelBrowser && !showDebug && (
              <SettingsPanel onClose={() => setShowSettings(false)} />
            )}
            {showModelBrowser && !showSettings && !showDebug && (
              <ModelBrowser onClose={() => setShowModelBrowser(false)} />
            )}
            {showDebug && !showSettings && !showModelBrowser && (
              <DebugPanel onClose={() => setShowDebug(false)} />
            )}
          </div>
        </div>
      </ErrorBoundary>
    </ServiceStatusProvider>
  );
}
