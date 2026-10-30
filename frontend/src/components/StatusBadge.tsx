import type { ChargeStatus } from "../api";
import { STATUS_LABEL } from "../format";

export function StatusBadge({ status }: { status: ChargeStatus }) {
  return (
    <span className={`badge badge-${status}`}>
      {status === "processing" && <span className="spinner" aria-hidden />}
      {STATUS_LABEL[status]}
    </span>
  );
}
