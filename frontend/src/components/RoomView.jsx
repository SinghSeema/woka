/** Room view component for active voice session. */

import React from "react";
import {
  LiveKitRoom,
  ParticipantTile,
  RoomAudioRenderer,
  ControlBar,
  useTracks,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Track } from "livekit-client";
import { BOT_NAME } from "../utils/constants";

/**
 * Stage component showing participants.
 */
function Stage() {
  const trackRefs = useTracks([Track.Source.Microphone]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
      {trackRefs.map((ref) => {
        const isBot = ref.participant.identity === BOT_NAME;
        return (
          <div
            key={`${ref.participant.sid}_${ref.source}`}
            className={`rounded-2xl overflow-hidden shadow-lg transition-all duration-300 ${
              isBot
                ? "bg-gradient-to-br from-green-100 to-emerald-100 border-2 border-green-300"
                : "bg-white border border-gray-200"
            }`}
          >
            <ParticipantTile
              trackRef={ref}
              className="w-full h-full"
            />
          </div>
        );
      })}
    </div>
  );
}

/**
 * Room view component.
 * @param {Object} props - Component props
 * @param {Object} props.roomData - Room connection data
 * @param {Function} props.onDisconnect - Callback when disconnecting
 */
export function RoomView({ roomData, onDisconnect }) {
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
      className="h-screen w-screen flex flex-col bg-gradient-to-br from-green-50 to-emerald-50"
    >
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h2 className="text-xl font-semibold text-gray-800">Wellness Session</h2>
      </div>

      <div className="flex-1 overflow-auto">
        <Stage />
      </div>

      <div className="bg-white border-t border-gray-200 px-6 py-4">
        <ControlBar
          variation="minimal"
          controls={{
            microphone: true,
            leave: true,
            camera: false,
            screenShare: false,
            chat: false,
          }}
        />
      </div>

      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

