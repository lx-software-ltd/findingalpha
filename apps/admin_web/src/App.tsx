import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./components/AuthProvider";
import { AuthenticatedShell } from "./components/AuthenticatedShell";
import { RequireAuth } from "./components/RequireAuth";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { MethodologyPage } from "./pages/MethodologyPage";
import { KnowledgeBasePage } from "./pages/KnowledgeBasePage";
import { RoadmapPage } from "./pages/RoadmapPage";
import { ScreenPage } from "./pages/ScreenPage";
import { SystemPage } from "./pages/SystemPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AuthenticatedShell />}>
                <Route index element={<RoadmapPage />} />
                <Route path="system" element={<SystemPage />} />
                <Route path="methodology" element={<MethodologyPage />} />
                <Route path="knowledge-base" element={<KnowledgeBasePage />} />
                <Route path="screen" element={<ScreenPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
