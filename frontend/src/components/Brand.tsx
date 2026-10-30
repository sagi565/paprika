export function Brand({ large = false }: { large?: boolean }) {
  return (
    <div className={large ? "brand brand-lg" : "brand"}>
      <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
        <path d="M16 9c-5 0-9 3.5-9 9.5S11 29 16 29s9-5 9-10.5S21 9 16 9z" fill="var(--accent)" />
        <path d="M16 9c0-3 1.5-5 4-6" stroke="var(--leaf)" strokeWidth="2.4" fill="none" strokeLinecap="round" />
      </svg>
      <div className="brand-text">
        <span className="brand-name">פפריקה</span>
        <span className="brand-sub">פירות וירקות</span>
      </div>
    </div>
  );
}
