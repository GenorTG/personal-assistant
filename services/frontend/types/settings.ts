// Settings types

export interface UserProfile {
  name?: string;
  about?: string;
  preferences?: string;
}

export interface CharacterCard {
  name?: string;
  personality?: string;
  background?: string;
  instructions?: string;
}

export interface AppSettings {
  user_profile?: UserProfile;
  character_card?: CharacterCard;
  llm_endpoint_mode?: string;
  llm_remote_url?: string;
  llm_remote_api_key?: string;
  llm_remote_model?: string;
  streaming_mode?: string;
  [key: string]: unknown;
}

export interface SettingsContextData {
  settings: AppSettings | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  modelLoaded: boolean;
  currentModel: string | null;
  userName: string | null;
  botName: string | null;
  supportsToolCalling: boolean;
}




