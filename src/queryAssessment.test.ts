import { describe, expect, it } from "vitest";
import { assessBrowserQuery } from "./queryAssessment";

describe("browser query assessment", () => {
  it("allows reads without confirmation", () => {
    expect(assessBrowserQuery("SELECT * FROM customers", false)).toMatchObject({ operation: "read", requiresConfirmation: false });
  });

  it("requires profile opt-in and confirmation for changes", () => {
    expect(() => assessBrowserQuery("DELETE FROM customers", false)).toThrow(/read-only/i);
    expect(assessBrowserQuery("DELETE FROM customers", true)).toMatchObject({ operation: "delete", destructive: true, requiresConfirmation: true });
  });

  it("detects data-changing CTEs and rejects stacked statements", () => {
    expect(assessBrowserQuery("WITH expired AS (SELECT id FROM sessions) DELETE FROM sessions WHERE id IN (SELECT id FROM expired)", true).operation).toBe("delete");
    expect(() => assessBrowserQuery("SELECT 1; DROP TABLE customers", true)).toThrow(/one SQL statement/i);
  });
});
