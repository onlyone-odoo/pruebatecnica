# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _default_company_id(self):
    """Return the company of the current environment."""
    return self.env.company


class SaleChannel(models.Model):
    """Sales channel that drives the delivery warehouse and the invoice journal.

    The code is assigned from the ``sale.channel`` sequence (``CH000001``).
    The specification wording mentions the sequence growing "per customer";
    the field lives on the channel, so a new number is consumed for every
    channel that is created.
    """

    _name = 'sale.channel'
    _description = 'Sales Channel'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code, id'
    _check_company_auto = True

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        readonly=True,
        copy=False,
        index=True,
        default='/',
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        check_company=True,
        ondelete='restrict',
        help='Delivery orders of sales on this channel are taken from this warehouse.',
    )
    invoice_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Invoice Journal',
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        check_company=True,
        ondelete='restrict',
        help='Customer invoices created from a sales order of this channel use this journal.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=_default_company_id,
        index=True,
    )

    _sql_constraints = [
        (
            'code_unique',
            'unique(code)',
            'The sales channel code must be unique.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Assign the next channel sequence when the code is left empty."""
        for vals in vals_list:
            if not vals.get('code') or vals.get('code') == '/':
                vals['code'] = self._next_code()
        return super().create(vals_list)

    @api.model
    def _next_code(self):
        """Return the next value of the sales channel sequence.

        :return: Code such as ``CH000001``.
        :rtype: str
        :raise UserError: if the sequence is missing.
        """
        code = self.env['ir.sequence'].next_by_code('sale.channel')
        if not code:
            raise UserError(_("The sales channel sequence is not configured."))
        return code
