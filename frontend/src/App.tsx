import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useStore } from "@/lib/store";
import { useEffect, useRef } from "react";
import { WebSocketManager } from "@/lib/api";
import Index from "./pages/Index";
import Incidents from "./pages/Incidents";
import Metrics from "./pages/Metrics";
import Remediations from "./pages/Remediations";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

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
    <TooltipProvider>
      <Sonner />
      <BrowserRouter>
        <AppLayout />
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
