# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SaleChannelCreditCommon


@tagged('post_install', '-at_install')
class TestSaleOrderCredit(SaleChannelCreditCommon):
    """Credit state, confirmation block and channel propagation."""

    def test_credit_state_and_blocked_confirmation(self):
        """The state follows the available credit and blocks confirmation."""
        channel = self._create_channel('Limited Channel')
        self._create_group(self.partner, channel, 'LIMIT-1', 100.0)

        blocked = self._create_order(self.partner, channel, 150.0)
        self.assertEqual(blocked.credit_state, 'blocked')
        with self.assertRaises(UserError):
            blocked.action_confirm()
        self.assertEqual(blocked.state, 'draft')

        allowed = self._create_order(self.partner, channel, 40.0)
        self.assertEqual(allowed.credit_state, 'available')
        allowed.action_confirm()
        self.assertEqual(allowed.state, 'sale')
        self.assertEqual(allowed.credit_state, 'available')

        group = self.partner.credit_group_ids
        group.invalidate_recordset(['used_credit', 'available_credit'])
        self.assertEqual(group.used_credit, 40.0)
        self.assertEqual(group.available_credit, 60.0)

        second = self._create_order(self.partner, channel, 70.0)
        self.assertEqual(second.credit_state, 'blocked')
        with self.assertRaises(UserError):
            second.action_confirm()

    def test_missing_group_keeps_no_limit(self):
        """No group for the customer or the channel means there is no limit."""
        channel = self._create_channel('Open Channel')
        other_channel = self._create_channel('Other Channel')
        free_partner = self.env['res.partner'].create({'name': 'Free Customer'})

        free_order = self._create_order(free_partner, channel, 999.0)
        self.assertEqual(free_order.credit_state, 'no_limit')
        free_order.action_confirm()
        self.assertEqual(free_order.state, 'sale')

        self._create_group(self.partner, channel, 'OTHER-1', 10.0)
        other_order = self._create_order(self.partner, other_channel, 999.0)
        self.assertEqual(other_order.credit_state, 'no_limit')
        other_order.action_confirm()

    def test_warehouse_and_journal_are_propagated(self):
        """The channel warehouse and journal reach the delivery and the invoice."""
        warehouse = self.env['stock.warehouse'].create({
            'name': 'Channel Warehouse',
            'code': 'CWH',
        })
        journal = self.env['account.journal'].create({
            'name': 'Channel Sales',
            'code': 'CHNS',
            'type': 'sale',
        })
        channel = self._create_channel(
            'Warehouse Channel',
            warehouse=warehouse,
            journal=journal,
        )
        order = self._create_order(
            self.partner,
            channel,
            50.0,
            product=self.storable_product,
        )
        self.assertEqual(order.warehouse_id, warehouse)
        self.assertEqual(order.journal_id, journal)

        order.action_confirm()
        self.assertTrue(order.picking_ids)
        self.assertEqual(order.picking_ids.channel_id, channel)
        self.assertEqual(
            set(order.picking_ids.picking_type_id.warehouse_id.ids),
            {warehouse.id},
        )

        invoice = order._create_invoices()
        self.assertEqual(invoice.journal_id, journal)
        self.assertEqual(invoice.channel_id, channel)

        form = self.env['sale.order'].get_view(
            view_id=self.env.ref('sale.view_order_form').id,
            view_type='form',
        )
        self.assertIn('credit_state', form['arch'])
        self.assertIn('channel_id', form['arch'])
        sale_list = self.env['sale.order'].get_view(
            view_id=self.env.ref('sale.view_order_tree').id,
            view_type='list',
        )
        self.assertIn('credit_state', sale_list['arch'])
        picking_search = self.env['stock.picking'].get_view(
            view_id=self.env.ref('stock.view_picking_internal_search').id,
            view_type='search',
        )
        self.assertIn('group_by_channel_id', picking_search['arch'])
        invoice_search = self.env['account.move'].get_view(
            view_id=self.env.ref('account.view_account_invoice_filter').id,
            view_type='search',
        )
        self.assertIn('group_by_channel_id', invoice_search['arch'])
