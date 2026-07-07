import { useCallback, useEffect, useState } from "react";
import { adminHealth, setSourceEnabled } from "../api";
import type { Me, SourceState } from "../types";

interface Health {
  sources: SourceState[];
  counts: Record<string, number>;
}

export default function AdminPage({ me }: { me: Me | null }) {
  const [health, setHealth] = useState<Health | null>(null);

  const reload = useCallback(() => {
    adminHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (me?.is_admin) reload();
  }, [me, reload]);

  if (!me?.is_admin) return <p>אין הרשאה</p>;

  async function toggle(source: SourceState) {
    await setSourceEnabled(source.source, !source.enabled);
    reload();
  }

  return (
    <div>
      <h2>ניהול</h2>
      {health && (
        <>
          <div className="card">
            <span className="badge">משתמשים: {health.counts.users}</span>
            <span className="badge">התראות: {health.counts.alerts}</span>
            <span className="badge">מודעות: {health.counts.listings}</span>
          </div>
          {health.sources.map((source) => (
            <div className="card" key={source.source}>
              <h3>{source.source}</h3>
              <p className="muted">
                {source.enabled ? "פעיל" : "כבוי"} · ריצה מוצלחת אחרונה: {source.last_success ?? "אף פעם"}
              </p>
              {source.last_error && <p className="error">{source.last_error}</p>}
              <button className="secondary" onClick={() => toggle(source)}>
                {source.enabled ? "השבתה" : "הפעלה"}
              </button>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
