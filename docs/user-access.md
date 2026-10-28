# User invitations and email verification

Public signup is disabled by default. An administrator can configure the
organization, create accounts, assign access, and manage site-wide settings in
the Administration area at `/app/admin/users/`.

1. Sign in with an MSConnect admin account and open **Administration**.
2. In **Labs**, add any missing university, facility, and lab records in that
   order. Existing active organization records are shown below the forms.
3. In **Users**, enter the person's username and email, select their lab, and choose both their
   application-wide role and lab role. Use the `admin` role only for people who
   should administer MSConnect.
4. MSConnect emails a one-time invitation. The account remains inactive until
   the recipient opens it and sets a password. Completing setup also verifies
   the email address.
5. Existing users with unverified email can select their account and choose
   **Resend verification**. Users signed in to their own account can use
   **Resend verification email** in the pending-verification banner.

For public signup (only if intentionally enabled), a verification message is
sent after account creation. The link opens an MSConnect confirmation page and
is valid for seven days. If it expires, the user can request a resend or an
administrator can resend it from User access.

Use the **Global settings** tab for system-wide processing defaults and mail
delivery status. The neighboring **Operations** page is for project-level
pipeline settings, releases, and lifecycle history.

## Email delivery

Configure SMTP in the environment used by the web container. The `.env.example`
file lists the variables; set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL` to values for
your mail provider. Keep credentials in the deployment's private `.env`, not in
source control. Set `MSCONNECT_EMAIL_FAIL_SILENT=0` so delivery failures are
reported to the UI. If delivery fails, an admin can use the secure fallback
link displayed by the admin page and pass it directly to the intended user.

The application-wide role controls site-level permissions. Lab membership role
and active status control a user's lab access. Django `is_superuser` is separate
and is intentionally not editable from this application screen.
