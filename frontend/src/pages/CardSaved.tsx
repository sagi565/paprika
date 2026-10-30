import { Brand } from "../components/Brand";
import { CheckIcon } from "../components/icons";

/** Public page (no login): Grow sends the kindergarten here after the card-save page. */
export function CardSaved() {
  const cancelled = new URLSearchParams(window.location.search).has("cancelled");
  return (
    <div className="login">
      <div className="login-card public-card">
        <Brand large />
        {cancelled ? (
          <>
            <h2>שמירת הכרטיס בוטלה</h2>
            <p className="sub">לא נשמר כרטיס. אפשר לפתוח שוב את הקישור שקיבלתם ולנסות שוב.</p>
          </>
        ) : (
          <>
            <span className="public-check">
              <CheckIcon size={28} />
            </span>
            <h2>תודה! הכרטיס נשמר</h2>
            <p className="sub">החשבון החודשי יחויב מעכשיו אוטומטית, והחשבונית תישלח אליכם כרגיל.</p>
          </>
        )}
      </div>
    </div>
  );
}
