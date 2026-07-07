import { useCallback, useEffect, useState } from "react";
import { getMe, logout } from "./api";
import AdminPage from "./pages/AdminPage";
import AlertsPage from "./pages/AlertsPage";
import SearchPage from "./pages/SearchPage";
import type { Me } from "./types";
import { useHashRoute } from "./useHashRoute";

export default function App() {
  const route = useHashRoute();
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refreshMe = useCallback(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(refreshMe, [refreshMe]);

  async function onLogout() {
    await logout();
    setMe(null);
  }

  return (
    <div>
      <nav className="nav">
        <a href="#/">חיפוש</a>
        <a href="#/alerts">ההתראות שלי</a>
        {me?.is_admin && <a href="#/admin">ניהול</a>}
        <span className="spacer" />
        {loaded && me && (
          <span className="user">
            {me.email} <button className="secondary" onClick={onLogout}>יציאה</button>
          </span>
        )}
        {loaded && !me && <a href="/api/auth/login">התחברות עם Google</a>}
      </nav>
      <main className="container">
        {route === "/alerts" ? (
          <AlertsPage me={me} />
        ) : route === "/admin" ? (
          <AdminPage me={me} />
        ) : (
          <SearchPage />
        )}
      </main>
    </div>
  );
}
