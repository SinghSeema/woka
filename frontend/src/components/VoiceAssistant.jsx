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
  const [roomData, setRoomData]       = useState(null);
  const [isLoading, setIsLoading]     = useState(true);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isReady, setIsReady]         = useState(false);

  useEffect(() => {
    healthCheck()
      .then(() => setIsLoading(false))
      .catch((error) => {
        logError(error, "VoiceAssistant");
        setIsLoading(false);
      });
  }, []);

  // Phase 2: handleConnect now receives languageCode from LandingPage
  const handleConnect = async (userName, languageCode = "en") => {
    try {
      const data = await getToken(userName, languageCode);
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

  return <LandingPage onConnect={handleConnect} />;
}