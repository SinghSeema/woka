/** Connecting/Loading view component - Shows while pipeline initializes. */

import React, { useState, useEffect, useRef } from "react";
import {
  LiveKitRoom,
  useParticipants,
  useRoomContext,
  useConnectionState,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { ConnectionState } from "livekit-client";
import { BOT_NAME } from "../utils/constants";
import { RoomContent } from "./RoomView";

/**
 * Inner component that uses LiveKit hooks to detect connection state
 */
function ConnectingContent({ onReady, onError }) {
  const connectionState = useConnectionState();
  const participants = useParticipants();
  const [botPresent, setBotPresent] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [checkCount, setCheckCount] = useState(0);
  const hasBeenConnectedRef = useRef(false);
  const errorSentRef = useRef(false);
  // Cloud Run agent may cold-start when min-instances=0.
  const BOT_JOIN_MAX_CHECKS = 120; // ~120s max wait after connected

  // Track elapsed time
  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedTime((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Check for bot participant when connected
  useEffect(() => {
    if (connectionState === ConnectionState.Connected) {
      hasBeenConnectedRef.current = true;
      const bot = participants.find(
        (p) => p.identity === BOT_NAME || p.name === BOT_NAME
      );

      if (bot) {
        setBotPresent(true);
        errorSentRef.current = false;
        // Give pipeline a moment to fully initialize (Shadow Memory, etc.)
        const timer = setTimeout(() => {
          if (onReady) onReady();
        }, 1000); // 1 second after bot detected
        return () => clearTimeout(timer);
      } else {
        // Keep checking for bot while worker cold-starts
        if (checkCount < BOT_JOIN_MAX_CHECKS) {
          const timer = setTimeout(() => {
            setCheckCount((prev) => prev + 1);
          }, 1000);
          return () => clearTimeout(timer);
        } else {
          // Timeout - bot didn't join
          if (onError && !errorSentRef.current) {
            errorSentRef.current = true;
            onError(new Error("Bot failed to join the room"));
          }
        }
      }
    } else if (connectionState === ConnectionState.Disconnected) {
      // Only treat disconnected as an error if we were previously connected
      // (disconnected is the initial state before connection starts)
      if (hasBeenConnectedRef.current && onError) {
        onError(new Error("Connection lost"));
      }
    }
  }, [connectionState, participants, botPresent, checkCount, onReady, onError]);

  useEffect(() => {
    if (connectionState === ConnectionState.Connecting) {
      setCheckCount(0);
      setBotPresent(false);
      errorSentRef.current = false;
      hasBeenConnectedRef.current = false;
    }
  }, [connectionState]);

  const isConnecting = connectionState === ConnectionState.Connecting;
  const isConnected = connectionState === ConnectionState.Connected;
  const showBotReady = botPresent && isConnected;

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        {/* Logo/Brand */}
        <div className="mb-8">
          <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center shadow-lg">
            <span className="text-4xl">🌿</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-800 mb-2">
            {BOT_NAME}
          </h1>
          <p className="text-gray-600">Wellness Voice Assistant</p>
        </div>

        {/* Connection Status */}
        <div className="bg-white rounded-2xl shadow-xl p-8 mb-6">
          {isConnecting && (
            <>
              <div className="relative w-16 h-16 mx-auto mb-6">
                <div className="absolute inset-0 border-4 border-green-200 rounded-full"></div>
                <div className="absolute inset-0 border-4 border-green-600 rounded-full border-t-transparent animate-spin"></div>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                Connecting...
              </h2>
              <p className="text-gray-600 text-sm">
                Initializing your wellness session
              </p>
            </>
          )}

          {isConnected && !showBotReady && (
            <>
              <div className="relative w-16 h-16 mx-auto mb-6">
                <div className="absolute inset-0 border-4 border-green-200 rounded-full"></div>
                <div className="absolute inset-0 border-4 border-green-600 rounded-full border-t-transparent animate-spin"></div>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                Preparing Session...
              </h2>
              <p className="text-gray-600 text-sm">
                Loading your conversation history
              </p>
              {elapsedTime > 3 && (
                <p className="text-xs text-gray-500 mt-2">
                  This may take a few seconds...
                </p>
              )}
            </>
          )}

          {showBotReady && (
            <>
              <div className="w-16 h-16 mx-auto mb-6">
                <div className="w-full h-full rounded-full bg-green-500 flex items-center justify-center animate-pulse">
                  <svg
                    className="w-8 h-8 text-white"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                </div>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">
                Ready!
              </h2>
              <p className="text-gray-600 text-sm">
                Your session is starting...
              </p>
            </>
          )}
        </div>

        {/* Participants Preview */}
        {isConnected && participants.length > 0 && (
          <div className="bg-white rounded-xl shadow-lg p-4">
            <p className="text-xs text-gray-500 mb-2">Participants</p>
            <div className="flex justify-center gap-2">
              {participants.map((participant) => (
                <div
                  key={participant.identity}
                  className="w-10 h-10 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center text-white font-semibold"
                  title={participant.name || participant.identity}
                >
                  {participant.name
                    ? participant.name.charAt(0).toUpperCase()
                    : participant.identity.charAt(0).toUpperCase()}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Loading Steps */}
        {isConnecting && (
          <div className="mt-6 space-y-2 text-left">
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span>Connecting to room...</span>
            </div>
          </div>
        )}

        {isConnected && !showBotReady && (
          <div className="mt-6 space-y-2 text-left">
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <div className="w-2 h-2 rounded-full bg-green-500"></div>
              <span>Connected to room</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span>Initializing pipeline...</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-gray-400">
              <div className="w-2 h-2 rounded-full bg-gray-300"></div>
              <span>Loading conversation history</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Connecting view component that shows loading state while pipeline initializes.
 * Transitions to RoomView when connection is ready and bot is present.
 */
export function ConnectingView({ roomData, onReady, onError, onDisconnect, showRoomView = false }) {
  if (!roomData) {
    return null;
  }

  return (
    <LiveKitRoom
      video={false}
      audio={true}
      token={roomData.token}
      serverUrl={roomData.url}
      connect={true}
      onError={(error) => {
        // Ignore "Client initiated disconnect" errors - these happen during React StrictMode cleanup
        // and shouldn't be treated as real connection errors
        if (error?.message?.includes("Client initiated disconnect")) {
          return;
        }
        console.error("LiveKit connection error:", error);
        if (onError) onError(error);
      }}
      className={showRoomView ? "h-screen w-screen flex flex-col bg-[#1a1a1a]" : "h-screen w-screen flex flex-col bg-gradient-to-br from-green-50 to-emerald-50"}
    >
      {showRoomView ? (
        <RoomContent onDisconnect={onDisconnect} />
      ) : (
        <>
          <ConnectingContent onReady={onReady} onError={onError} />
          
          {/* Footer */}
          <div className="bg-white/50 border-t border-gray-200 px-6 py-4 text-center">
            <p className="text-xs text-gray-500">
              Powered by LiveKit • Secure & Private
            </p>
          </div>
        </>
      )}
    </LiveKitRoom>
  );
}

