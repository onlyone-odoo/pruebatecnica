# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import psycopg2

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import SaleChannelCreditCommon


@tagged('post_install', '-at_install')
class TestCreditGroup(SaleChannelCreditCommon):
    """Code rules and the used / available credit amounts."""

    def test_code_cannot_contain_026(self):
        """The substring 026 is rejected and nearby codes are accepted."""
        channel = self._create_channel('Code Channel')
        with self.assertRaises(ValidationError):
            self.env['sale.credit.group'].create({
                'name': 'Forbidden',
                'code': 'AA026BB',
                'channel_id': channel.id,
                'global_credit': 10.0,
            })
        allowed = self.env['sale.credit.group'].create({
            'name': 'Allowed',
            'code': '0206',
            'channel_id': channel.id,
            'global_credit': 10.0,
        })
        self.assertEqual(allowed.code, '0206')

    def test_code_is_unique(self):
        """The same code cannot be used by two groups."""
        channel = self._create_channel('Unique Channel')
        self.env['sale.credit.group'].create({
            'name': 'First',
            'code': 'UNIQUE-1',
            'channel_id': channel.id,
            'global_credit': 10.0,
        })
        # The SQL constraint is reported as a database error inside tests.
        # The HTTP service turns the same constraint into a validation error.
        with self.assertRaises(psycopg2.IntegrityError), self.cr.savepoint():
            self.env['sale.credit.group'].create({
                'name': 'Second',
                'code': 'UNIQUE-1',
                'channel_id': channel.id,
                'global_credit': 20.0,
            })

    def test_partner_requires_a_group_when_control_is_enabled(self):
        """Credit control without a group is rejected."""
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'Controlled Without Group',
                'credit_control': True,
            })

    def test_used_credit_converts_foreign_currency_without_double_count(self):
        """A foreign sale and its open invoice consume the credit once."""
        currency = self._activate_foreign_currency()
        pricelist = self.env['product.pricelist'].create({
            'name': 'Foreign Pricelist',
            'currency_id': currency.id,
            'company_id': self.company.id,
        })
        self.partner.property_product_pricelist = pricelist
        channel = self._create_channel('Foreign Channel')
        group = self._create_group(self.partner, channel, 'FX-1', 1000.0)

        order = self._create_order(self.partner, channel, 100.0)
        self.assertEqual(order.currency_id, currency)
        self.assertNotEqual(order.currency_id, self.company.currency_id)
        order.action_confirm()

        expected = self._company_amount(
            order.amount_total,
            order.currency_id,
            order._credit_conversion_date(),
        )
        self.assertNotEqual(expected, order.amount_total)
        group.invalidate_recordset(['used_credit', 'available_credit'])
        self.assertEqual(group.used_credit, expected)
        self.assertEqual(group.available_credit, 1000.0 - expected)

        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale_channel_credit.report_credit_group',
            group.ids,
        )
        if isinstance(html, bytes):
            html = html.decode()
        self.assertIn(group.code, html)
        self.assertIn(self.partner.name, html)
        self.assertIn(self.partner.vat, html)
        self.assertIn(order.name, html)

        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.channel_id, channel)
        self.assertTrue(order.currency_id.is_zero(order._get_credit_uninvoiced_amount()))
        group.invalidate_recordset(['used_credit', 'available_credit'])
        self.assertEqual(group.used_credit, expected)
        self.assertEqual(group.available_credit, 1000.0 - expected)

        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale_channel_credit.report_credit_group',
            group.ids,
        )
        if isinstance(html, bytes):
            html = html.decode()
        self.assertIn(invoice.name, html)
        self.assertNotIn(order.name, html)

    def test_open_invoice_without_sale_order_is_converted(self):
        """An unpaid customer invoice in another currency consumes credit."""
        currency = self._activate_foreign_currency()
        channel = self._create_channel('Invoice Channel')
        group = self._create_group(self.partner, channel, 'FX-INV', 500.0)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'channel_id': channel.id,
            'currency_id': currency.id,
            'invoice_date': fields.Date.context_today(self.partner),
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id,
                'name': 'Foreign service',
                'quantity': 1.0,
                'price_unit': 80.0,
                'tax_ids': [Command.clear()],
            })],
        })
        invoice.action_post()
        expected = self._company_amount(invoice.amount_residual, currency, invoice.invoice_date)
        self.assertNotEqual(expected, invoice.amount_residual)
        group.invalidate_recordset(['used_credit', 'available_credit'])
        self.assertEqual(group.used_credit, expected)
        self.assertEqual(group.available_credit, 500.0 - expected)
