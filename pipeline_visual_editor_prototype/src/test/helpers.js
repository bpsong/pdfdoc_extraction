// Shared test helpers and mock factories

/** Build a minimal finding object */
export function makeFinding({ severity = "error", code = "test-code", path = "test.path", message = "Test message" } = {}) {
  return { severity, code, path, message };
}

/** Build a minimal step object */
export function makeStep({ key = "test_step", label = "Test Step", module = "standard_step.test", class: cls = "TestTask", enabled = true, on_error = "stop", params = {} } = {}) {
  return { key, label, module, class: cls, enabled, on_error, params };
}
