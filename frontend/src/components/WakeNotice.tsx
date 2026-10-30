import { useEffect, useState } from "react";
import { WAKING_EVENT } from "../api";

/** "Server is waking up" pill, shown while requests are being retried. */
export function WakeNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onWaking = () => {
      setVisible(true);
      clearTimeout(timer);
      timer = setTimeout(() => setVisible(false), 6000);
    };
    window.addEventListener(WAKING_EVENT, onWaking);
    return () => {
      window.removeEventListener(WAKING_EVENT, onWaking);
      clearTimeout(timer);
    };
  }, []);

  if (!visible) return null;
  return (
    <div className="wake-notice" role="status">
      <span className="spinner" aria-hidden />
      השרת מתעורר, עוד רגע…
    </div>
  );
}
