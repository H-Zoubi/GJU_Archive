"""
Mark accounts created before `is_gju_verified` was set at signup.

Every account that exists today was created through the login view's stubbed
`verify_with_gju`, which trusts any first-time credentials. Those accounts
passed exactly the same check as one created now -- the flag simply was not
written. Leaving them False locks the site's own early users out of every
download, so they are backfilled to match the rule actually in force.

When the real GJU verifier lands this is NOT the precedent to follow: accounts
from that point on are verified because GJU said so, and a failed check must
leave the flag False.
"""
from django.db import migrations


def mark_existing_accounts_verified(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_gju_verified=False).update(is_gju_verified=True)


def unmark(apps, schema_editor):
    # Deliberately a no-op: we cannot tell which accounts this migration
    # touched from those verified legitimately afterwards, and clearing the
    # wrong ones would lock real students out.
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.RunPython(mark_existing_accounts_verified, unmark),
    ]
