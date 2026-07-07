import { useCallback, useEffect, useState } from "react";
import {
  createAlert, deleteAccount, deleteAlert, listAlerts,
  mintTelegramLink, setAlertActive, updateAlert,
} from "../api";
import {
  EMPTY_FILTERS, FilterForm, alertFiltersToValues, filtersToAlertFilters, type FilterValues,
} from "../components/FilterForm";
import type { Alert, Me } from "../types";

function summarize(alert: Alert): string {
  const parts = [alert.filters.locations.map((location) => location.neighborhood ?? location.city).join(", ")];
  if (alert.filters.max_price != null) parts.push(`עד ₪${alert.filters.max_price.toLocaleString("he-IL")}`);
  if (alert.filters.min_rooms != null || alert.filters.max_rooms != null) {
    parts.push(`${alert.filters.min_rooms ?? "?"}-${alert.filters.max_rooms ?? "?"} חדרים`);
  }
  return parts.join(" · ");
}

export default function AlertsPage({ me }: { me: Me | null }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [editing, setEditing] = useState<Alert | "new" | null>(null);
  const [name, setName] = useState("");
  const [values, setValues] = useState<FilterValues>(EMPTY_FILTERS);
  const [channels, setChannels] = useState<string[]>(["email"]);
  const [telegramLink, setTelegramLink] = useState<{ link: string; expires_minutes: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listAlerts().then(setAlerts).catch(() => setError("שגיאה בטעינת ההתראות"));
  }, []);

  useEffect(() => {
    if (me) reload();
  }, [me, reload]);

  if (!me) {
    return (
      <div>
        <h2>ההתראות שלי</h2>
        <p>
          כדי לשמור התראות צריך <a href="/api/auth/login">התחברות עם Google</a>.
        </p>
      </div>
    );
  }

  function openNew() {
    setEditing("new");
    setName("");
    setValues(EMPTY_FILTERS);
    setChannels(me!.telegram_linked ? ["telegram", "email"] : ["email"]);
  }

  function openEdit(alert: Alert) {
    setEditing(alert);
    setName(alert.name);
    setValues(alertFiltersToValues(alert.filters));
    setChannels(alert.channels);
  }

  async function save() {
    setError(null);
    if (channels.length === 0) {
      setError("צריך לבחור לפחות ערוץ אחד");
      return;
    }
    const body = { name: name.trim(), filters: filtersToAlertFilters(values), channels };
    try {
      if (editing === "new") await createAlert(body);
      else if (editing) await updateAlert(editing.id, body);
      setEditing(null);
      reload();
    } catch {
      setError("שמירת ההתראה נכשלה");
    }
  }

  function toggleChannel(channel: string) {
    setChannels((current) =>
      current.includes(channel) ? current.filter((existing) => existing !== channel) : [...current, channel]
    );
  }

  async function onToggle(alert: Alert) {
    await setAlertActive(alert.id, !alert.active);
    reload();
  }

  async function onDelete(alert: Alert) {
    if (window.confirm("למחוק את ההתראה?")) {
      await deleteAlert(alert.id);
      reload();
    }
  }

  async function onLinkTelegram() {
    setTelegramLink(await mintTelegramLink());
  }

  async function onDeleteAccount() {
    if (window.confirm("למחוק את החשבון וכל ההתראות לצמיתות?")) {
      await deleteAccount();
      window.location.hash = "#/";
      window.location.reload();
    }
  }

  return (
    <div>
      <h2>ההתראות שלי</h2>
      {error && <p className="error">{error}</p>}
      {!me.telegram_linked && (
        <div className="card">
          {telegramLink ? (
            <p>
              <a href={telegramLink.link} target="_blank" rel="noopener noreferrer">פתיחת הבוט בטלגרם</a>
              {" "}— הקישור תקף ל-{telegramLink.expires_minutes} דקות.
            </p>
          ) : (
            <button onClick={onLinkTelegram}>חיבור טלגרם</button>
          )}
        </div>
      )}
      {editing === null && <button onClick={openNew}>התראה חדשה</button>}
      {editing !== null && (
        <div className="card">
          <label htmlFor="alert-name">שם ההתראה</label>
          <input id="alert-name" type="text" value={name}
                 onChange={(event) => setName(event.target.value)} />
          <FilterForm value={values} onChange={setValues} onSubmit={save} submitLabel="שמירה" />
          <div>
            <label className="checkbox">
              <input type="checkbox" checked={channels.includes("telegram")}
                     onChange={() => toggleChannel("telegram")} /> טלגרם
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={channels.includes("email")}
                     onChange={() => toggleChannel("email")} /> אימייל
            </label>
          </div>
          <button className="secondary" onClick={() => setEditing(null)}>ביטול</button>
        </div>
      )}
      {alerts.map((alert) => (
        <div className="card" key={alert.id}>
          <h3>{alert.name}</h3>
          <p className="muted">{summarize(alert)}</p>
          <div>
            {alert.channels.map((channel) => (
              <span className="badge" key={channel}>{channel === "telegram" ? "טלגרם" : "אימייל"}</span>
            ))}
            {!alert.active && <span className="badge">מושהית</span>}
          </div>
          <button className="secondary" onClick={() => onToggle(alert)}>
            {alert.active ? "השהיה" : "הפעלה"}
          </button>{" "}
          <button className="secondary" onClick={() => openEdit(alert)}>עריכה</button>{" "}
          <button className="danger" onClick={() => onDelete(alert)}>מחיקה</button>
        </div>
      ))}
      <div className="card">
        <h3>אזור מסוכן</h3>
        <button className="danger" onClick={onDeleteAccount}>מחיקת חשבון</button>
      </div>
    </div>
  );
}
