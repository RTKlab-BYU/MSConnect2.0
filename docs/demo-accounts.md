# Demo Accounts

Seed them with:

```sh
.venv/bin/python manage.py seed_demo_showcase
```

Login at:

```text
/accounts/login/
```

All demo logins use:

```text
Password: DemoPass-2026!
```

Accounts:

- `demo-admin` - admin/operator access
- `demo-pi` - PI/research lead access
- `demo-researcher` - researcher access
- `demo-collaborator` - collaborator access

Notes:

- The seed command also keeps a legacy `parkerreyes` admin account for compatibility with older tests.
- These accounts are idempotent; rerunning the seed command resets the password to the same value.
