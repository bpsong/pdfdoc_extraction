# Property pane UX audit — round 2

Scope: remaining rules, archive, PDF storage, and JSON storage task properties, plus shared task actions.

1. Failure behavior — replaced raw `stop`/`continue` values with “Stop the pipeline” and “Continue to the next task”, plus a consequence sentence that updates with the selection.
2. Task removal — replaced immediate deletion with an inline confirmation that names the task and explains that its draft settings will be removed.
3. Rules outcome — added a live plain-language summary of the selected destination field, written value, and number of required conditions.
4. Match conditions — numbered each condition, stated that all conditions use AND logic, and gave each remove button a unique accessible name and minimum-condition explanation.
5. Archive destination — clarified that the task copies the original PDF using a safe, unique filename and leaves the source in place.

Visual evidence: `01-rules-before.png` captures the rules pane before this pass. The improved states were inspected directly in the running editor; DOM evidence confirmed the updated labels, summaries, condition names, archive explanation, and confirmation state.

Interaction checks: failure behavior was changed and restored; the explanatory sentence updated both times. The removal confirmation was opened and cancelled without deleting the task. Screenshot-only review cannot establish full keyboard, screen-reader, contrast, or zoom conformance.
