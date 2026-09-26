import { getStatusClass } from "../utils/validationErrors";

type StatusBadgeProps = {
  status?: string | null;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={getStatusClass(status)}>{status ?? "Not started"}</span>;
}
