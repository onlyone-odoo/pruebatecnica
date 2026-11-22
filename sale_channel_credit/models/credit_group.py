# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


def _default_company_id(self):
    """Return the company of the current environment."""
    return self.env.company


class SaleCreditGroup(models.Model):
    """Credit limit shared by the customers of one sales channel.

    Used credit is always expressed in the company currency. It is the sum of:

    * the not-yet-invoiced tax-included amount of confirmed sales orders of
      the group's customers on this channel, and
    * the residual of posted, unpaid customer invoices and credit notes of
      those customers on this channel.

    Documents are limited to the group's channel so the same sale is not
    consumed by every group a customer belongs to. The not-yet-invoiced
    portion (instead of the whole order total) avoids counting an amount
    both on the order and on the open invoice.
    """

    _name = 'sale.credit.group'
    _description = 'Credit Group'
    _order = 'code, id'
    _check_company_auto = True

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, index=True)
    channel_id = fields.Many2one(
        comodel_name='sale.channel',
        string='Sales Channel',
        required=True,
        ondelete='restrict',
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=_default_company_id,
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
    )
    global_credit = fields.Monetary(
        string='Global Credit',
        currency_field='currency_id',
        required=True,
        help='Credit granted to the whole group, in the company currency.',
    )
    used_credit = fields.Monetary(
        string='Used Credit',
        currency_field='currency_id',
        compute='_compute_used_credit',
        help='Confirmed sales not yet invoiced plus open customer invoices, '
             'in the company currency.',
    )
    available_credit = fields.Monetary(
        string='Available Credit',
        currency_field='currency_id',
        compute='_compute_available_credit',
    )
    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        relation='sale_credit_group_partner_rel',
        column1='credit_group_id',
        column2='partner_id',
        string='Customers',
    )

    _sql_constraints = [
        (
            'code_unique',
            'unique(code)',
            'The credit group code must be unique.',
        ),
    ]

    @api.constrains('code')
    def _check_code(self):
        """Reject an empty code and any code that contains ``026``."""
        for group in self:
            code = group.code or ''
            if not code.strip():
                raise ValidationError(_("The credit group code is required."))
            if '026' in code:
                raise ValidationError(_(
                    "The credit group code cannot contain the sequence \"026\"."
                ))

    @api.depends('partner_ids', 'channel_id', 'company_id')
    def _compute_used_credit(self):
        """Compute used credit from open sales orders and customer invoices."""
        for group in self:
            group.used_credit = group._get_used_credit_amount()

    @api.depends('global_credit', 'used_credit')
    def _compute_available_credit(self):
        for group in self:
            group.available_credit = group.currency_id.round(
                group.global_credit - group.used_credit
            )

    def _get_used_credit_amount(self):
        """Return the used credit of this group in company currency.

        :return: Rounded company-currency amount.
        :rtype: float
        """
        self.ensure_one()
        currency = self.company_id.currency_id
        amount = 0.0
        for order in self.get_credit_sale_orders():
            amount += order._get_credit_uninvoiced_amount_company_currency()
        amount += sum(self.get_credit_invoices().mapped('amount_residual_signed'))
        return currency.round(amount) if currency else amount

    def _credit_partner_domain(self):
        """Domain leaf that selects the customers and their contacts.

        :return: A single domain leaf. Callers must not use it when the
            group has no customers.
        :rtype: tuple
        """
        self.ensure_one()
        return ('partner_id', 'child_of', self.partner_ids.ids)

    def get_credit_sale_orders(self):
        """Return confirmed sales orders that still consume credit.

        Draft and cancelled orders are ignored. Fully invoiced orders
        contribute nothing here; their open invoices are returned by
        :meth:`get_credit_invoices`.

        Sales users do not always have access to every order of the
        customer. The credit figure has to include all of them, so the
        search runs in sudo and is still limited to this company and
        channel.

        :return: ``sale.order`` recordset.
        """
        self.ensure_one()
        if not self.partner_ids or not self.channel_id:
            return self.env['sale.order']
        orders = self.env['sale.order'].sudo().search([
            self._credit_partner_domain(),
            ('channel_id', '=', self.channel_id.id),
            ('state', 'in', ('sale', 'done')),
            ('company_id', '=', self.company_id.id),
        ])
        return orders.filtered(
            lambda order: not order.currency_id.is_zero(
                order._get_credit_uninvoiced_amount()
            )
        )

    def get_credit_invoices(self):
        """Return open customer invoices and credit notes that consume credit.

        ``in_payment`` is excluded: a payment has already been registered.
        Credit notes reduce used credit because ``amount_residual_signed``
        is negative.

        :return: ``account.move`` recordset.
        """
        self.ensure_one()
        if not self.partner_ids or not self.channel_id:
            return self.env['account.move']
        invoices = self.env['account.move'].sudo().search([
            self._credit_partner_domain(),
            ('channel_id', '=', self.channel_id.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('company_id', '=', self.company_id.id),
        ])
        return invoices.filtered(
            lambda move: not move.company_currency_id.is_zero(move.amount_residual_signed)
        )

    def _get_matching_groups(self, partner, channel):
        """Return the groups of ``partner`` that apply to ``channel``.

        :param partner: Customer to inspect.
        :param channel: Sales channel of the order.
        :return: Matching credit groups of the partner's company.
        """
        if not partner or not channel or not partner.credit_control:
            return self.browse()
        return partner.credit_group_ids.filtered(
            lambda group: group.channel_id == channel
            and group.company_id == channel.company_id
        )

    def action_open_credit_orders(self):
        """Open the sales orders counted in the used credit."""
        self.ensure_one()
        orders = self.get_credit_sale_orders()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sales Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
        }

    def action_open_credit_invoices(self):
        """Open the invoices counted in the used credit."""
        self.ensure_one()
        invoices = self.get_credit_invoices()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoices.ids)],
        }


def credit_exceeds(amount, available, currency):
    """Return whether ``amount`` is strictly greater than ``available``.

    :param float amount: Order total in ``currency``.
    :param float available: Credit still available in ``currency``.
    :param currency: Company currency used for the rounding.
    :return: True when the sale must be blocked.
    :rtype: bool
    """
    rounding = currency.rounding if currency else 0.01
    return float_compare(amount, available, precision_rounding=rounding) > 0
