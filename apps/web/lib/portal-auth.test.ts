import { describe, expect, it } from "vitest";
import { recoveryCode, verifyRecoveryCode } from "./portal-auth";

describe("recovery codes", () => {
  it("creates a short-lived code without storing the password", async () => {
    const secret = "a-secure-session-secret-with-more-than-32-characters";
    const email = "admin@example.com";
    const code = await recoveryCode(email, secret);
    expect(code).toMatch(/^[A-Z0-9]{8}$/);
    expect(await verifyRecoveryCode(email, code.toLowerCase(), secret)).toBe(true);
    expect(await verifyRecoveryCode(email, "INVALID1", secret)).toBe(false);
  });
});
