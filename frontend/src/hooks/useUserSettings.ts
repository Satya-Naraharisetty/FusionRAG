import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./useAuth";
import {
  getUserSettings,
  patchUserSettings,
  UserSettingsPatchRequest,
  UserSettingsResponse,
} from "../api/userSettings";
import { useEffect, useMemo } from "react";

const USER_SETTINGS_QUERY_KEY = "user-settings";
const SYNC_CHANNEL_NAME = "fusion_rag_user_sync";

export const useUserSettings = () => {
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  const queryKey = useMemo(
    () => [USER_SETTINGS_QUERY_KEY, user?.id],
    [user?.id]
  );

  // Helper to read local per-user cached fallback
  const getLocalCache = (): UserSettingsResponse | null => {
    if (!user?.id) return null;
    try {
      const saved = localStorage.getItem(`user_${user.id}_settings`);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  };

  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const data = await getUserSettings();
      // Update per-user cache
      if (user?.id) {
        try {
          localStorage.setItem(`user_${user.id}_settings`, JSON.stringify(data));
        } catch {
          // Ignore
        }
      }
      return data;
    },
    enabled: isAuthenticated && Boolean(user?.id),
    initialData: () => getLocalCache() ?? undefined,
    staleTime: 60 * 1000, // 1 minute
  });

  // Listen to multi-tab BroadcastChannel updates
  useEffect(() => {
    if (typeof window === "undefined" || !("BroadcastChannel" in window) || !user?.id) {
      return;
    }

    const channel = new BroadcastChannel(SYNC_CHANNEL_NAME);
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === "USER_SETTINGS_UPDATED" && e.data?.userId === user.id) {
        queryClient.invalidateQueries({ queryKey });
      }
    };

    channel.addEventListener("message", handleMessage);
    return () => {
      channel.removeEventListener("message", handleMessage);
      channel.close();
    };
  }, [user?.id, queryClient, queryKey]);

  return query;
};

export const useUpdateUserSettings = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const queryKey = [USER_SETTINGS_QUERY_KEY, user?.id];

  return useMutation({
    mutationFn: async (patch: UserSettingsPatchRequest) => {
      return patchUserSettings(patch);
    },
    onMutate: async (newPatch: UserSettingsPatchRequest) => {
      // Cancel outgoing refetches so they don't overwrite optimistic update
      await queryClient.cancelQueries({ queryKey });

      const previous = queryClient.getQueryData<UserSettingsResponse>(queryKey);

      if (previous) {
        const optimistic: UserSettingsResponse = {
          ...previous,
          folders: newPatch.folders ?? previous.folders,
          pinned_conversations:
            newPatch.pinned_conversations ?? previous.pinned_conversations,
          conversation_tags:
            newPatch.conversation_tags ?? previous.conversation_tags,
          document_folders:
            newPatch.document_folders ?? previous.document_folders,
          document_folder_mappings:
            newPatch.document_folder_mappings ?? previous.document_folder_mappings,
          document_custom_order:
            newPatch.document_custom_order ?? previous.document_custom_order,
          document_filter_presets:
            newPatch.document_filter_presets ?? previous.document_filter_presets,
          preferences: newPatch.preferences
            ? { ...previous.preferences, ...newPatch.preferences }
            : previous.preferences,
          updated_at: new Date().toISOString(),
        };

        queryClient.setQueryData<UserSettingsResponse>(queryKey, optimistic);

        // Update local cache
        if (user?.id) {
          try {
            localStorage.setItem(
              `user_${user.id}_settings`,
              JSON.stringify(optimistic)
            );
          } catch {
            // Ignore
          }
        }
      }

      return { previous };
    },
    onError: (_err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSettled: (data) => {
      queryClient.invalidateQueries({ queryKey });

      // Broadcast across tabs
      if (
        typeof window !== "undefined" &&
        "BroadcastChannel" in window &&
        user?.id
      ) {
        try {
          const channel = new BroadcastChannel(SYNC_CHANNEL_NAME);
          channel.postMessage({
            type: "USER_SETTINGS_UPDATED",
            userId: user.id,
            data,
          });
          channel.close();
        } catch {
          // Ignore
        }
      }
    },
  });
};
