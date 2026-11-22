# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleChannel(TransactionCase):
    """Sequence and chatter of the sales channel."""

    def test_sequence_assigns_readonly_codes(self):
        """Each channel receives the next CH###### code and a copy gets a new one."""
        sequence = self.env['ir.sequence'].search([
            ('code', '=', 'sale.channel'),
        ], limit=1)
        self.assertTrue(sequence)
        self.assertEqual(sequence.prefix, 'CH')
        self.assertEqual(sequence.padding, 6)
        self.assertTrue(self.env['sale.channel']._fields['code'].readonly)

        next_number = sequence.number_next_actual
        first = self.env['sale.channel'].create({'name': 'First Channel'})
        second = self.env['sale.channel'].create({'name': 'Second Channel'})
        self.assertEqual(first.code, 'CH%06d' % next_number)
        self.assertEqual(second.code, 'CH%06d' % (next_number + 1))
        self.assertRegex(first.code, r'^CH\d{6}$')

        copied = first.copy()
        self.assertNotEqual(copied.code, first.code)
        self.assertRegex(copied.code, r'^CH\d{6}$')

        view = self.env.ref('sale_channel_credit.view_sale_channel_form')
        self.assertIn('name="code"', view.arch)
        self.assertIn('readonly="1"', view.arch)

    def test_name_change_is_tracked(self):
        """Changing the name posts a tracking message on the chatter."""
        channel = self.env['sale.channel'].with_context(
            mail_notrack=False,
            tracking_disable=False,
        ).create({'name': 'Old Name'})
        self.env.flush_all()
        self.cr.flush()
        tracked_fields = channel._track_get_fields()
        channel.write({'name': 'New Name'})
        # Tracking values are created in a precommit hook.
        self.env.flush_all()
        self.cr.flush()
        channel.invalidate_recordset()
        tracked = channel.message_ids.tracking_value_ids
        self.assertTrue(
            tracked,
            "tracked_fields=%s messages=%s" % (
                tracked_fields,
                channel.message_ids.read(['body', 'message_type', 'subtype_id']),
            ),
        )
        self.assertIn('name', tracked.mapped('field_id.name'))
