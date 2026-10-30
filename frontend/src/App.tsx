import { useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { api, UNAUTHORIZED_EVENT, type Me } from "./api";
import { Brand } from "./components/Brand";
import { GroupIcon, HomeIcon, ReceiptIcon } from "./components/icons";
import { Toaster } from "./components/toast";
import { WakeNotice } from "./components/WakeNotice";
import { Billing } from "./pages/Billing";
import { Clients } from "./pages/Clients";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Send } from "./pages/Send";

function Layout({ me, onLogout, children }: { me: Me; onLogout: () => void; children: ReactNode }) {
  return (
    <>
      {me.grow_mode === "mock" && <div className="demo-strip">מצב הדגמה: החיובים והחשבוניות מדומים</div>}
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand-link" aria-label="דף הבית">
            <Brand />
          </Link>
          <nav className="nav">
            <NavLink to="/" end>
              בית
            </NavLink>
            <NavLink to="/billing">חיובים</NavLink>
            <NavLink to="/clients">גנים</NavLink>
          </nav>
          <button className="link-btn" onClick={onLogout}>
            יציאה
          </button>
        </div>
      </header>
      <main className="page">{children}</main>
      <nav className="tabbar" aria-label="ניווט">
        <NavLink to="/" end>
          <HomeIcon />
          בית
        </NavLink>
        <NavLink to="/billing">
          <ReceiptIcon />
          חיובים
        </NavLink>
        <NavLink to="/clients">
          <GroupIcon />
          גנים
        </NavLink>
      </nav>
    </>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);

  useEffect(() => {
    api.me().then(setMe, () => setMe(null));
    const onUnauthorized = () => setMe(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const logout = async () => {
    await api.logout().catch(() => undefined);
    setMe(null);
  };

  if (me === undefined) {
    return (
      <div className="boot boot-center">
        <Brand large />
        <WakeNotice />
      </div>
    );
  }

  return (
    <>
      {me === null ? (
        <Login onLogin={setMe} />
      ) : (
        <BrowserRouter>
          <Routes>
            <Route path="/send/:id" element={<Send />} />
            <Route
              path="*"
              element={
                <Layout me={me} onLogout={logout}>
                  <Routes>
                    <Route path="/" element={<Home />} />
                    <Route path="/billing" element={<Billing />} />
                    <Route path="/clients" element={<Clients />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Layout>
              }
            />
          </Routes>
        </BrowserRouter>
      )}
      <Toaster />
      <WakeNotice />
    </>
  );
}
