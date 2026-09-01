import { api } from "./client";

export interface FolderItem {
  id: string;
  name: string;
  conversationIds: string[];
  description?: string;
  color?: string;
}

export interface TagItem {
  name: string;
  color: string;
}

export interface DocumentFolderItem {
  id: string;
  name: string;
  color?: string;
  icon?: string;
}

export interface DocumentFilterPreset {
  id: string;
  name: string;
  filters: Record<string, unknown>;
}

export interface UserSettingsResponse {
  user_id: string;
  folders: FolderItem[];
  pinned_conversations: string[];
  conversation_tags: Record<string, TagItem[]>;
  document_folders: DocumentFolderItem[];
  document_folder_mappings: Record<string, string>;
  document_custom_order: string[];
  document_filter_presets: DocumentFilterPreset[];
  preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UserSettingsPatchRequest {
  folders?: FolderItem[];
  pinned_conversations?: string[];
  conversation_tags?: Record<string, TagItem[]>;
  document_folders?: DocumentFolderItem[];
  document_folder_mappings?: Record<string, string>;
  document_custom_order?: string[];
  document_filter_presets?: DocumentFilterPreset[];
  preferences?: Record<string, unknown>;
}

export const getUserSettings = async (): Promise<UserSettingsResponse> => {
  return api.get<UserSettingsResponse>("/user/settings");
};

export const patchUserSettings = async (
  data: UserSettingsPatchRequest,
): Promise<UserSettingsResponse> => {
  return api.patch<UserSettingsResponse>("/user/settings", data);
};
