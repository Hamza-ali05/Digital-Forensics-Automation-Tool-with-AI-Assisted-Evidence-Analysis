import { validateEmail, validatePassword } from "utils/validators";

describe("validators", () => {
  test("test_validatePassword_strong_passes", () => {
    const result = validatePassword("LifeCyclePass1!");
    expect(result.isValid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("test_validatePassword_weak_fails", () => {
    const result = validatePassword("short");
    expect(result.isValid).toBe(false);
    expect(result.errors.length).toBeGreaterThanOrEqual(4);
  });

  test("test_validateEmail_valid", () => {
    expect(validateEmail("investigator@lab.local")).toBe(true);
  });

  test("test_validateEmail_invalid", () => {
    expect(validateEmail("not-an-email")).toBe(false);
    expect(validateEmail("")).toBe(false);
  });
});
