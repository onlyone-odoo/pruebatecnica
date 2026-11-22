# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.tools import float_compare

from .credit_group import credit_exceeds


class SaleOrder(models.Model):
    """Sales channel, warehouse and credit state on the sales order."""

    _inherit = 'sale.order'

    channel_id = fields.Many2one(
        comodel_name='sale.channel',
        string='Sales Channel',
        required=True,
        ondelete='restrict',
        check_company=True,
        index=True,
        tracking=True,
    )
    credit_state = fields.Selection(
        selection=[
            ('no_limit', 'No Credit Limit'),
            ('available', 'Credit Available'),
            ('blocked', 'Credit Blocked'),
        ],
        string='Credit',
        compute='_compute_credit_state',
        default='no_limit',
        readonly=True,
        help='No Credit Limit: the customer has no credit group for this channel. '
             'Credit Available: the order total fits in the group. '
             'Credit Blocked: the order total exceeds the available credit.',
    )

    @api.depends('user_id', 'company_id', 'channel_id', 'channel_id.warehouse_id')
    def _compute_warehouse_id(self):
        """Apply the channel warehouse on quotations.

        ``state`` is intentionally not a dependency: the standard compute
        only assigns a warehouse while the order is a quotation, and adding
        ``state`` would recompute the field on confirmation. A confirmed
        order keeps the warehouse stored on it.
        """
        super()._compute_warehouse_id()
        for order in self:
            channel_warehouse = order.channel_id.warehouse_id
            if channel_warehouse and (order.state in ('draft', 'sent') or not order.ids):
                order.warehouse_id = channel_warehouse
                continue
            if order.state not in ('draft', 'sent') and order._origin:
                # The standard compute does not assign the field once the
                # order is confirmed. Assign the stored value so this
                # override does not clear it when the channel changes.
                order.warehouse_id = order._origin.warehouse_id

    @api.depends(
        'sale_order_template_id',
        'channel_id',
        'channel_id.invoice_journal_id',
    )
    def _compute_journal_id(self):
        """Use the invoice journal defined on the sales channel."""
        super()._compute_journal_id()
        for order in self:
            journal = order.channel_id.invoice_journal_id
            if journal:
                order.journal_id = journal

    @api.depends(
        'partner_id',
        'partner_id.credit_control',
        'partner_id.credit_group_ids',
        'partner_id.credit_group_ids.global_credit',
        'partner_id.credit_group_ids.channel_id',
        'partner_id.commercial_partner_id.credit_control',
        'partner_id.commercial_partner_id.credit_group_ids',
        'partner_id.commercial_partner_id.credit_group_ids.global_credit',
        'partner_id.commercial_partner_id.credit_group_ids.channel_id',
        'channel_id',
        'amount_total',
        'currency_id',
        'state',
        'company_id',
        'date_order',
        'invoice_ids.state',
        'invoice_ids.payment_state',
        'invoice_ids.amount_residual',
    )
    def _compute_credit_state(self):
        """Compare the order total with the available credit of the group.

        The group's used credit already includes this order once it is
        confirmed. That amount is added back before the comparison so a
        sale that fitted at confirmation does not turn blocked afterwards.
        """
        for order in self:
            order.credit_state = order._get_credit_state_value()

    def _get_credit_partner(self):
        """Return the partner evaluated for the credit check."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return partner
        return partner._get_credit_control_partner()

    def _get_credit_group(self):
        """Return the strictest credit group for this customer and channel.

        When the customer belongs to several groups of the same channel,
        the one with the lowest available credit is used.

        :return: Empty recordset or a single ``sale.credit.group``.
        """
        self.ensure_one()
        partner = self._get_credit_partner()
        groups = self.env['sale.credit.group']._get_matching_groups(
            partner, self.channel_id,
        )
        if not groups:
            return groups
        # Drop a stale cache: used credit depends on other documents.
        groups.invalidate_recordset(['used_credit', 'available_credit'])
        return min(groups, key=lambda group: (group.available_credit, group.id))

    def _get_credit_state_value(self):
        """Return the selection value of the credit state.

        :return: ``no_limit``, ``available`` or ``blocked``.
        :rtype: str
        """
        self.ensure_one()
        group = self._get_credit_group()
        if not group:
            return 'no_limit'
        order_amount = self._get_credit_total_company_currency()
        available = group.available_credit + self._get_credit_amount_already_counted()
        if credit_exceeds(order_amount, available, self.company_id.currency_id):
            return 'blocked'
        return 'available'

    def _get_credit_total_company_currency(self):
        """Return ``amount_total`` converted to the company currency.

        :rtype: float
        """
        self.ensure_one()
        company = self.company_id
        conversion_date = self._credit_conversion_date()
        return self.currency_id._convert(
            self.amount_total,
            company.currency_id,
            company,
            conversion_date,
        )

    def _get_credit_uninvoiced_amount(self):
        """Return the tax-included amount that is not invoiced yet.

        The value is in the order currency. A negative remainder (more
        invoiced than ordered, for example after a refund) counts as zero
        so the order does not reduce credit by itself; the credit note
        residual does that.

        :rtype: float
        """
        self.ensure_one()
        currency = self.currency_id
        remaining = self.amount_total - self.amount_invoiced
        if float_compare(remaining, 0.0, precision_rounding=currency.rounding) <= 0:
            return 0.0
        return currency.round(remaining)

    def _get_credit_uninvoiced_amount_company_currency(self):
        """Return the not-yet-invoiced amount in company currency.

        :rtype: float
        """
        self.ensure_one()
        company = self.company_id
        return self.currency_id._convert(
            self._get_credit_uninvoiced_amount(),
            company.currency_id,
            company,
            self._credit_conversion_date(),
        )

    def _get_credit_amount_already_counted(self):
        """Return this order's own contribution already included in used credit.

        :rtype: float
        """
        self.ensure_one()
        if self.state not in ('sale', 'done'):
            return 0.0
        counted = self._get_credit_uninvoiced_amount_company_currency()
        invoices = self.invoice_ids.filtered(
            lambda move: move.state == 'posted'
            and move.move_type in ('out_invoice', 'out_refund')
            and move.payment_state in ('not_paid', 'partial')
            and move.channel_id == self.channel_id
        )
        counted += sum(invoices.mapped('amount_residual_signed'))
        return self.company_id.currency_id.round(counted)

    def _credit_conversion_date(self):
        """Return the date used to convert this order to company currency."""
        self.ensure_one()
        if self.date_order:
            return fields.Date.to_date(self.date_order)
        return fields.Date.context_today(self)

    def _confirmation_error_message(self):
        """Block confirmation while the credit state is blocked."""
        self.ensure_one()
        self.invalidate_recordset(['credit_state'])
        if self.credit_state == 'blocked':
            return _(
                "You cannot confirm %(order)s because the credit of %(partner)s "
                "on channel %(channel)s is blocked.",
                order=self.display_name,
                partner=self.partner_id.display_name,
                channel=self.channel_id.display_name,
            )
        return super()._confirmation_error_message()

    def _action_confirm(self):
        """Copy the sales channel onto the deliveries created at confirmation."""
        result = super()._action_confirm()
        for order in self:
            pickings = order.picking_ids.filtered(
                lambda picking: picking.channel_id != order.channel_id
            )
            if order.channel_id and pickings:
                pickings.write({'channel_id': order.channel_id.id})
        return result

    def _prepare_invoice(self):
        """Propagate the channel and force its invoice journal."""
        self.ensure_one()
        values = super()._prepare_invoice()
        if self.channel_id:
            values['channel_id'] = self.channel_id.id
            if self.channel_id.invoice_journal_id:
                values['journal_id'] = self.channel_id.invoice_journal_id.id
        return values
