# Manage passwords and application settings

| Item | Value |
| --- | --- |
| Audience | Application administrators |
| Owner | Application maintainers |
| Status | Current |
| Last verified | 2026-10-10 — repository/source review; no live deployment check |
| Applies to | Current application screens |

The app has two fixed accounts, **admin** and **operator**. Their account names
and roles cannot be changed. IT/support sets their initial passwords.

## Change a password

1. Sign in as **admin** and select **Users**.
2. Choose the account card.
3. Enter the current **administrator** password in the first password field.
   This is required for either account. The Operator card currently labels
   this field **Current Operator password**, but it requires the admin password.
4. Enter and confirm the new password.
5. Select **Change admin password** or **Change operator password**.
6. Check the confirmation. Existing sessions for the changed account are
   signed out; sign in again if you changed the admin password.

Use a unique password with uppercase and lowercase letters, a number and a
symbol. Ordinary English letters/numbers/symbols must total 12–72 characters;
other characters can reach the maximum sooner. Follow the displayed rules and
cooldown messages. The new password must differ from the current one.

If you cannot sign in as admin, ask IT/support to recover access. Recovery
replaces both account passwords, so arrange new details for operators too.
Share passwords through your organisation's approved channel.

## Change application settings

Open **Overview**, find **Non-secret Settings**, change a displayed value and
select **Save Settings**. Check the success or error message before leaving.
Use **Pipeline**, **Review Forms** and **Watch folders** for their own settings.
The former read-only Settings screen has been retired.

The currently listed settings have different purposes:

| Setting label | Admin advice |
| --- | --- |
| **Application Name** | Use a clear organisation/process name. This does not rename pipeline keys or fields. |
| **Default Page Size** | A positive list-size preference. Avoid very large values without checking usability on the deployment. |
| **Default Review Queue** | Keep the agreed queue, normally `default_review`. Pipeline tasks can have their own queue; changing this default does not rewrite published task definitions. |
| **Review Lock Timeout** | Minutes before an abandoned claim can expire, normally 60. Agree changes with the review team: too short can permit takeover during long checks; too long can delay recovery of abandoned work. |
| **Configuration Validation**, **Strict Mode Default**, **Allow UI Config Save** | Deployment-validation controls. Keep prepared values unless IT has agreed the effect; these do not publish pipeline/form drafts or test extraction quality. |

Change one setting at a time, record its previous value and check the intended
effect. Save Settings is separate from publishing pipeline or review-form
versions. A queue/default change should be tested against the task's own
settings before telling operators it applies to existing work.

Server addresses, certificates, external connections, installation paths and
settings absent from Overview belong with IT/support. Give them the required
outcome. Keep service keys and passwords out of description fields and screenshots.

For planned maintenance, ask operators to stop submitting and pause incoming
folders. Agree with IT how to handle work already accepted. After maintenance,
check Reports, Review Queue and folder health before resuming intake.
