# Authentication FAQ

## Login form reloads without sign-in

If the login page reloads and the user stays on the sign-in form, first verify that:

- the email and password are correct;
- the browser accepts cookies;
- the session cookie is not blocked by privacy extensions;
- the service status page does not report an authentication incident.

Recommended support action:

1. Ask the user to clear auth cookies for the service.
2. Ask the user to retry in a private browser window.
3. If the issue persists, check whether the account is locked or pending verification.

## Account locked after multiple attempts

The service temporarily locks the account after repeated failed sign-in attempts.

Recommended support action:

1. Confirm the lock in the ticket or security logs.
2. Ask the user to wait for the cooldown period or reset the password.
3. Escalate if the user confirms a successful password reset but the lock remains active.

## Password reset does not help

If a new password is rejected right after reset:

- confirm that the user opened the latest reset link;
- confirm that the password was not copied with trailing spaces;
- check whether the reset token expired before the user submitted the form.

## Two-factor code does not arrive

If the 2FA code does not arrive:

- check spam or quarantine folders;
- confirm the mailbox address on the account;
- verify there is no delivery incident on the notification side.
