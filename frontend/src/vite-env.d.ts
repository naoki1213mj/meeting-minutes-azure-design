/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AAD_CLIENT_ID?: string;
  readonly VITE_AAD_TENANT_ID?: string;
  readonly VITE_AAD_REDIRECT_URI?: string;
  readonly VITE_DEV_TENANT_ID?: string;
  readonly VITE_DEV_USER_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
