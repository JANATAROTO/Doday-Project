# Generated manually for REQ-13 (external API traceability fields)

import django.db.models.deletion
import django.db.models.expressions
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_event_ticket_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='external_source',
            field=models.CharField(
                blank=True,
                help_text="Source API slug (e.g. 'ticketmaster'). Empty for manually-created events.",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='event',
            name='external_id',
            field=models.CharField(
                blank=True,
                help_text='Original ID in the external source. Used together with external_source for deduplication.',
                max_length=100,
            ),
        ),
        migrations.AddConstraint(
            model_name='event',
            constraint=models.UniqueConstraint(
                condition=~models.Q(external_source=''),
                fields=['external_source', 'external_id'],
                name='unique_external_event',
            ),
        ),
    ]
