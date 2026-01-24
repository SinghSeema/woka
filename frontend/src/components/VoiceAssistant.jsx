/** Main Voice Assistant component. */

import React, { useState, useEffect } from "react";
import { LandingPage } from "./LandingPage";
import { RoomView } from "./RoomView";
import { getToken, healthCheck } from "../services/api";
import { handleApiError, logError } from "../utils/errorHandler";

/**
 * Main Voice Assistant component.
 */
export function VoiceAssistant() {
  const [roomData, setRoomData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

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
    } catch (error) {
      logError(error, "handleConnect");
      throw error;
    }
  };

  const handleDisconnect = () => {
    setRoomData(null);
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

  if (roomData) {
    return <RoomView roomData={roomData} onDisconnect={handleDisconnect} />;
  }

  return <LandingPage onConnect={handleConnect} />;
}

