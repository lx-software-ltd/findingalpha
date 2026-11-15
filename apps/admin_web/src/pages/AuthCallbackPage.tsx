import { useNavigate } from "react-router-dom";
import { useAuth } from "../components/AuthProvider";
import { useRunOncePerPageLoad } from "../hooks/useRunOncePerPageLoad";
import {
  clearStoredSession,
  LOGIN_DENIED_FLASH_KEY,
  loginDeniedMessage,
  NOT_AUTHORIZED_MESSAGE,
  OAUTH_STATE_KEY,
  PKCE_VERIFIER_KEY,
  saveTokensFromOAuthResponse,
} from "../lib/auth";
import { getAdminConfig } from "../lib/config";
import { idTokenHasAdminAccess } from "../lib/jwt";

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  useRunOncePerPageLoad("oauth-callback", () => {
    let cancelled = false;
    const run = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const state = params.get("state");
      const expectedState = sessionStorage.getItem(OAUTH_STATE_KEY);
      const isOurFlow = Boolean(
        state && expectedState && state === expectedState,
      );
      if (!code || !isOurFlow) {
        // A redirect that carries our `state` but no code is Cognito
        // reporting a refused sign-in (the user-pool gate raised); the
        // error text only selects the message shown on the login screen.
        if (isOurFlow) {
          sessionStorage.setItem(
            LOGIN_DENIED_FLASH_KEY,
            loginDeniedMessage(params.get("error_description")),
          );
        }
        sessionStorage.removeItem(PKCE_VERIFIER_KEY);
        sessionStorage.removeItem(OAUTH_STATE_KEY);
        navigate("/", { replace: true });
        return;
      }
      const verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
      if (!verifier) {
        navigate("/", { replace: true });
        return;
      }
      const cfg = getAdminConfig();
      const body = new URLSearchParams({
        grant_type: "authorization_code",
        client_id: cfg.clientId,
        code,
        redirect_uri: cfg.redirectUri,
        code_verifier: verifier,
      });
      const res = await fetch(`${cfg.cognitoDomain}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      if (!res.ok || cancelled) {
        sessionStorage.removeItem(PKCE_VERIFIER_KEY);
        sessionStorage.removeItem(OAUTH_STATE_KEY);
        navigate("/", { replace: true });
        return;
      }
      const json = (await res.json()) as {
        id_token: string;
        access_token: string;
        refresh_token?: string;
        expires_in: number;
      };
      if (!idTokenHasAdminAccess(json.id_token)) {
        clearStoredSession();
        sessionStorage.setItem(LOGIN_DENIED_FLASH_KEY, NOT_AUTHORIZED_MESSAGE);
        sessionStorage.removeItem(PKCE_VERIFIER_KEY);
        sessionStorage.removeItem(OAUTH_STATE_KEY);
        navigate("/", { replace: true });
        return;
      }
      saveTokensFromOAuthResponse({
        id_token: json.id_token,
        access_token: json.access_token,
        refresh_token: json.refresh_token,
        expires_in: json.expires_in,
      });
      sessionStorage.removeItem(PKCE_VERIFIER_KEY);
      sessionStorage.removeItem(OAUTH_STATE_KEY);
      refreshUser();
      navigate("/", { replace: true });
    };
    void run();
    return () => {
      cancelled = true;
    };
  });

  return (
    <div className="container py-5 text-center">
      <p className="text-muted">Completing sign-in…</p>
    </div>
  );
}
