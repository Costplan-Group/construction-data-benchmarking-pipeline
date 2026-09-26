import type { ValidationErrorRow } from "../types/ingestion";

export function toFriendlyErrorMessage(row: ValidationErrorRow): string {
  const errorType = (row.ErrorType ?? "").toUpperCase();
  const sheet = row.SheetName ?? "the sheet";
  const rowText = row.RowNum ? `row ${row.RowNum}` : "a row";
  const column = row.ColumnName ?? "a required field";

  if (errorType === "MISSING_TOTALCOST_SKIPPED") {
    return `In ${sheet}, ${rowText} has no value in ${column}. This row was skipped and not loaded. Add a total cost value for the selected contractor and re-upload.`;
  }

  if (errorType === "MISSING_COLUMN") {
    return `A required column is missing in ${sheet}. Add the expected column and upload again.`;
  }

  if (errorType === "INVALID_NUMBER") {
    return `A value in ${sheet} ${rowText} is not a valid number. Correct the numeric value and upload again.`;
  }

  if (errorType === "DOMAIN") {
    return `A value in ${sheet} ${rowText} is outside the allowed options. Check the accepted values and upload again.`;
  }

  if (errorType === "DECIMAL_PRECISION") {
    return `A numeric value in ${sheet} ${rowText} is too large or has too many decimal places for the database. Reduce precision and upload again.`;
  }

  if (errorType === "EXCEPTION") {
    return "The ingestion run failed unexpectedly. Review the technical message or contact support.";
  }

  return row.ErrorMessage ?? "Validation issue detected. Please review this row and try again.";
}

export function severityLabel(value?: string | null): string {
  const s = (value ?? "").toUpperCase();
  if (s === "ERROR") {
    return "Error";
  }
  if (s === "WARNING") {
    return "Warning";
  }
  return value ?? "-";
}

export function getStatusClass(status?: string | null): string {
  const value = (status ?? "").toUpperCase();
  if (value === "COMMITTED" || value === "VALIDATED") {
    return "status-badge status-success";
  }
  if (value === "FAILED" || value === "ERROR") {
    return "status-badge status-error";
  }
  if (value === "STAGED" || value === "RECEIVED") {
    return "status-badge status-warning";
  }
  return "status-badge status-neutral";
}
