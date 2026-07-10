import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LanguageProvider } from "./lib/i18n";
import { Layout } from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Agents from "./pages/Agents";
import AgentDetail from "./pages/AgentDetail";
import ADLEditor from "./pages/ADLEditor";
import Generator from "./pages/Generator";
import Doctrine from "./pages/Doctrine";
import Events from "./pages/Events";
import Audit from "./pages/Audit";
import Monitoring from "./pages/Monitoring";
import Users from "./pages/Users";

const Protected = ({ children }) => {
  const { user } = useAuth();
  if (user === null) return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-primary font-mono text-xs animate-pulse tracking-[0.3em] uppercase">CVLN Agent Factory</p></div>;
  if (user === false) return <Navigate to="/login" replace />;
  return children;
};

function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:agentId" element={<AgentDetail />} />
              <Route path="/editor" element={<ADLEditor />} />
              <Route path="/generator" element={<Generator />} />
              <Route path="/doctrine" element={<Doctrine />} />
              <Route path="/events" element={<Events />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="/monitoring" element={<Monitoring />} />
              <Route path="/users" element={<Users />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster theme="dark" position="bottom-right" toastOptions={{ style: { background: "hsl(240 10% 6%)", border: "1px solid hsl(240 10% 15%)", color: "hsl(0 0% 98%)", borderRadius: "2px", fontFamily: "'JetBrains Mono', monospace", fontSize: "12px" } }} />
      </AuthProvider>
    </LanguageProvider>
  );
}

export default App;
