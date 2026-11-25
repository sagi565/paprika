import { Brand } from "../components/Brand";
import { CheckIcon, CloseIcon } from "../components/icons";

/** Public page (no login): Grow sends the kindergarten here after the card-save page. */
export function CardSaved() {
  const cancelled = new URLSearchParams(window.location.search).has("cancelled");
  return (
    <div className="solo">
      <div className="solo-card">
        <Brand size="md" tagline />
        {cancelled ? (
          <>
            <span className="solo-icon solo-icon-muted">
              <CloseIcon size={26} />
            </span>
            <h1>שמירת הכרטיס בוטלה</h1>
            <p>לא נשמר כרטיס. אפשר לפתוח שוב את הקישור שקיבלתם ולנסות שוב.</p>
          </>
        ) : (
          <>
            <span className="solo-icon">
              <CheckIcon size={28} />
            </span>
            <h1>הכרטיס נשמר בהצלחה</h1>
            <p>החיוב החודשי יתבצע מעכשיו בלחיצה, בלי להקליד את הכרטיס שוב. אפשר לסגור את הלשונית.</p>
          </>
        )}
      </div>
    </div>
  );
}
