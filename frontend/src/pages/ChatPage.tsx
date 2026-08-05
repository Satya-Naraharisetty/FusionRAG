import React from "react";
import { useParams } from "react-router-dom";
import { ChatView } from "../components/chat/ChatView";

const ChatPage: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();

  return (
    <div className="flex-1 flex flex-col h-full w-full overflow-hidden">
      <ChatView conversationId={conversationId || null} />
    </div>
  );
};

export default ChatPage;
