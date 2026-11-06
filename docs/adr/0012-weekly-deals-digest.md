---
status: proposed
---

# A weekly deals digest by platform: opt-in, separate from wishlist alerts

Once a week, users who ask for it get the week's best deals on their platforms, by e-mail and, when they turned it on, by push. We decided to:

- **Opt in**, off by default, and separate from the wishlist alerts (`users.wish_alerts`), which stay as they are. Someone may want one without the other.
- **Their platforms**: by default the platforms of the games they own, editable in the account.
- **What it lists**: up to 10 of the biggest real discounts ([ADR 0003](0003-real-discounts.md)) that started in the last 7 days, and editions that reached a new historical low in those days. Each has its store, price and discount, and links to our game page. Games the user owns are left out, and games on their wishlist are marked.
- **When**: after the first full run on or after Monday. A `digest_sent_at` per user makes sure it goes out once a week at most. A week with nothing to list sends nothing.
- **The existing channels**: `app/services/mail_service.py` for e-mail and `app/services/push_service.py` for push, with a signed "turn it off" link, as `app/services/wish_alert_service.py` does.
- **Three new columns on users**, in an Alembic revision: whether it's on, the chosen platforms, and when it was last sent.

## Considered options

- **A daily digest.** Rejected: the header's bell and the wishlist alerts already cover daily news, and most real discounts last several days.
- **Adding it to the wishlist alerts.** Rejected: people agree to e-mails about their own wishes, not to general deals. The digest needs its own yes.

## Consequences

- It depends on the full run happening. On the PC, where runs depend on the computer being on, it may arrive later in the week.
- Until `SMTP_HOST` is set, it's written to the log instead of sent, like every e-mail.
- The data export (`app/services/export_service.py`) must include the digest settings.
