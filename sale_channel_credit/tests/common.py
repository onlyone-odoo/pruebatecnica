# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class SaleChannelCreditCommon(TransactionCase):
    """Shared customers, products and a loaded chart of accounts."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(
            cls.env.context,
            tracking_disable=True,
            mail_create_nolog=True,
        ))
        cls.company = cls.env.company
        if not cls.company.chart_template:
            cls.env['account.chart.template'].try_loading(
                'generic_coa',
                cls.company,
                install_demo=False,
            )
        cls.product = cls.env['product.product'].create({
            'name': 'Credit Service',
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 100.0,
            'taxes_id': [Command.clear()],
        })
        cls.storable_product = cls.env['product.product'].create({
            'name': 'Storable Goods',
            'type': 'consu',
            'is_storable': True,
            'invoice_policy': 'order',
            'list_price': 50.0,
            'taxes_id': [Command.clear()],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Credit Customer',
            'vat': '20123456789',
            'phone': '+54 11 0000-0000',
            'email': 'customer@example.com',
        })

    @classmethod
    def _create_channel(cls, name, warehouse=None, journal=None):
        """Create a sales channel.

        :param str name: Channel name.
        :param warehouse: Optional ``stock.warehouse``.
        :param journal: Optional sale journal.
        :return: ``sale.channel`` record.
        """
        values = {'name': name}
        if warehouse:
            values['warehouse_id'] = warehouse.id
        if journal:
            values['invoice_journal_id'] = journal.id
        return cls.env['sale.channel'].create(values)

    @classmethod
    def _create_group(cls, partner, channel, code, credit, name='Credit Group'):
        """Create a group and enable credit control on ``partner``.

        :return: ``sale.credit.group`` record.
        """
        group = cls.env['sale.credit.group'].create({
            'name': name,
            'code': code,
            'channel_id': channel.id,
            'global_credit': credit,
        })
        partner.write({
            'credit_control': True,
            'credit_group_ids': [Command.link(group.id)],
        })
        return group

    def _create_order(self, partner, channel, price, product=None):
        """Create a one-line sales order without taxes.

        :param float price: Unit price in the order currency.
        :return: ``sale.order`` record.
        """
        return self.env['sale.order'].create({
            'partner_id': partner.id,
            'channel_id': channel.id,
            'order_line': [Command.create({
                'product_id': (product or self.product).id,
                'product_uom_qty': 1.0,
                'price_unit': price,
                'tax_id': [Command.clear()],
            })],
        })

    def _activate_foreign_currency(self):
        """Activate a currency whose rate is not 1 and return it.

        The stored rate is 2, so the converted amount differs from the
        document amount. The exact company-currency value is obtained with
        ``_convert`` inside the test.

        :return: ``res.currency`` record.
        """
        currency = self.env.ref('base.EUR')
        if currency == self.company.currency_id:
            currency = self.env.ref('base.GBP')
        self.env['res.currency.rate'].search([
            ('currency_id', '=', currency.id),
            ('company_id', '=', self.company.id),
        ]).unlink()
        currency.active = True
        self.env['res.currency.rate'].create({
            'name': '2020-01-01',
            'rate': 2.0,
            'currency_id': currency.id,
            'company_id': self.company.id,
        })
        return currency

    def _company_amount(self, amount, currency, conversion_date=None):
        """Convert ``amount`` to the company currency.

        :rtype: float
        """
        conversion_date = conversion_date or fields.Date.context_today(self)
        return currency._convert(
            amount,
            self.company.currency_id,
            self.company,
            conversion_date,
        )
