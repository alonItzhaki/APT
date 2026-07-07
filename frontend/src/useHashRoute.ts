import { useEffect, useState } from "react";

function currentRoute(): string {
  return window.location.hash.replace(/^#/, "") || "/";
}

export function useHashRoute(): string {
  const [route, setRoute] = useState(() => currentRoute());
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
