import { BUSINESS as B } from "../business";

/** On every page: Grow's site review wants the contact phone and a terms link on the home page. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>
        {B.name} · {B.owner} · עוסק מורשה {B.businessId}
      </span>
      <span>{B.address}</span>
      <a href={`tel:${B.phone.replace(/\D/g, "")}`}>טלפון: {B.phone}</a>
      <a href={`mailto:${B.email}`}>{B.email}</a>
      <a href="/terms">תקנון ותנאי שירות</a>
    </footer>
  );
}
