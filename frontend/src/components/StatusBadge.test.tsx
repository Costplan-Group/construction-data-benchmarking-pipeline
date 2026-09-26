import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders status text with the success class for COMMITTED", () => {
    render(<StatusBadge status="COMMITTED" />);
    const badge = screen.getByText("COMMITTED");
    expect(badge).toHaveClass("status-badge", "status-success");
  });

  it("falls back to Not started when status is missing", () => {
    render(<StatusBadge />);
    expect(screen.getByText("Not started")).toHaveClass("status-badge", "status-neutral");
  });
});
