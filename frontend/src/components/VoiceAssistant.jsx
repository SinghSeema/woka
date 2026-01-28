/** Main Voice Assistant component. */

import React, { useState, useEffect } from "react";
import { LandingPage } from "./LandingPage";
import { ConnectingView } from "./ConnectingView";
import { RoomView } from "./RoomView";
import { getToken, healthCheck } from "../services/api";
import { handleApiError, logError } from "../utils/errorHandler";

/**
 * Main Voice Assistant component.
 * Manages state flow: LandingPage -> ConnectingView -> RoomView
 */
export function VoiceAssistant() {
  const [roomData, setRoomData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // Health check on mount
    healthCheck()
      .then(() => {
        setIsLoading(false);
      })
      .catch((error) => {
        logError(error, "VoiceAssistant");
        setIsLoading(false);
      });
  }, []);

  const handleConnect = async (userName) => {
    try {
      const data = await getToken(userName);
      setRoomData(data);
      setIsConnecting(true);
      setIsReady(false);
    } catch (error) {
      logError(error, "handleConnect");
      throw error;
    }
  };

  const handleConnectingReady = () => {
    setIsReady(true);
    setIsConnecting(false);
  };

  const handleConnectingError = (error) => {
    console.error("Connection error:", error);
    setIsConnecting(false);
    setRoomData(null);
    // Could show error toast here
  };

  const handleDisconnect = () => {
    setRoomData(null);
    setIsConnecting(false);
    setIsReady(false);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  // Show connecting view while pipeline initializes, or room view when ready
  // Keep ConnectingView mounted to maintain the same LiveKitRoom connection
  if (roomData && (isConnecting || isReady)) {
    return (
      <ConnectingView
        roomData={roomData}
        onReady={handleConnectingReady}
        onError={handleConnectingError}
        onDisconnect={handleDisconnect}
        showRoomView={isReady}
      />
    );
  }

  // Show landing page
  return <LandingPage onConnect={handleConnect} />;
}

