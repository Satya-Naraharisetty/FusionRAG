export const KEYBOARD_SHORTCUTS = {
  NEW_CHAT: "ctrl+n",
  SEARCH: "ctrl+/",
  COMMAND_PALETTE: "ctrl+k",
  DOCUMENTS: "ctrl+shift+o",
  SETTINGS: "ctrl+shift+s",
  FOCUS_INPUT: "/",
};

export const UPLOAD_LIMITS = {
  MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
  ACCEPTED_TYPES: {
    "application/pdf": [".pdf"],
    "text/plain": [".txt"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "text/markdown": [".md"],
  },
};

export const QUERY_KEYS = {
  CONVERSATIONS: "conversations",
  MESSAGES: "messages",
  DOCUMENTS: "documents",
  EMBEDDING_STATUS: "embedding_status",
};
