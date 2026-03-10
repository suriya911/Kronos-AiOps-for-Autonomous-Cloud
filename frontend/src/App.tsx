import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useStore } from "@/lib/store";
import { useEffect, useRef, useState } from "react";
import { WebSocketManager } from "@/lib/api";
import { isAuthenticated, handleCallback, login } from "@/lib/auth";
import Index from "./pages/Index";
import Incidents from "./pages/Incidents";
import Metrics from "./pages/Metrics";
import Remediations from "./pages/Remediations";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

// ─── AuthGuard ────────────────────────────────────────────────────────────────
// Handles OAuth2 PKCE callback and gates all app content behind authentication.
// In mock mode (VITE_USE_MOCK=true) auth is bypassed entirely.

function AuthGuard({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(USE_MOCK); // skip auth in mock mode
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    if (USE_MOCK) return;

    const params = new URLSearchParams(window.location.search);
    if (params.has('code') && params.has('state')) {
      // OAuth callback — exchange code for tokens
      handleCallback()
        .then(() => {
          window.history.replaceState({}, '', '/');
          setReady(true);
        })
        .catch((err: unknown) => {
          console.error('[Auth] Callback failed:', err);
          login().catch((e: unknown) => {
            setAuthError(e instanceof Error ? e.message : String(e));
          });
        });
    } else if (!isAuthenticated()) {
      login().catch((err: unknown) => {
        console.error('[Auth] Login failed:', err);
        setAuthError(err instanceof Error ? err.message : String(err));
      });
    } else {
      setReady(true);
    }
  }, []);

  if (authError) {
    return (
      <div className="min-h-screen flex items-center justify-center dark bg-background">
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="w-10 h-10 rounded-full bg-destructive/20 flex items-center justify-center">
            <span className="text-destructive text-xl font-bold">!</span>
          </div>
          <h2 className="text-lg font-semibold text-foreground">Auth Configuration Error</h2>
          <p className="text-sm text-muted-foreground font-mono bg-muted rounded p-3 text-left break-words">{authError}</p>
          <p className="text-xs text-muted-foreground">
            Add <code>VITE_COGNITO_DOMAIN</code> and <code>VITE_COGNITO_CLIENT_ID</code> to your Vercel project environment variables.
          </p>
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center dark bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">Authenticating…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry:                1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppLayout() {
  const { sidebarCollapsed, setWsStatus } = useStore();
  const wsRef = useRef<WebSocketManager | null>(null);

  // Real WebSocket connection with automatic exponential-backoff reconnection.
  // Falls back to a simulated "CONNECTED" in mock mode or when no WS URL is set.
  useEffect(() => {
    const WS_URL   = import.meta.env.VITE_WS_URL as string | undefined;
    const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

    if (!WS_URL || USE_MOCK) {
      const timer = setTimeout(() => setWsStatus('CONNECTED'), 1500);
      return () => clearTimeout(timer);
    }

    const manager = new WebSocketManager(WS_URL, { setWsStatus }, queryClient);
    wsRef.current  = manager;
    manager.connect();

    return () => manager.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen flex w-full dark">
      <Sidebar />
      <div className={`flex-1 flex flex-col transition-all duration-300 ${sidebarCollapsed ? 'ml-16' : 'ml-60'}`}>
        <Topbar />
        <main className="flex-1 p-6 overflow-y-auto">
          <Routes>
            <Route path="/"             element={<Index />} />
            <Route path="/incidents"    element={<Incidents />} />
            <Route path="/metrics"      element={<Metrics />} />
            <Route path="/remediations" element={<Remediations />} />
            <Route path="/settings"     element={<Settings />} />
            <Route path="*"             element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthGuard>
      <TooltipProvider>
        <Sonner />
        <BrowserRouter>
          <AppLayout />
        </BrowserRouter>
      </TooltipProvider>
    </AuthGuard>
  </QueryClientProvider>
);

export default App;
