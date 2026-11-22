# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class AccountMove(models.Model):
    """Sales channel propagated from the sales order onto the invoice."""

    _inherit = 'account.move'

    channel_id = fields.Many2one(
        comodel_name='sale.channel',
        string='Sales Channel',
        index=True,
        ondelete='restrict',
        check_company=True,
        copy=True,
        help='Sales channel of the order that originated this customer invoice.',
    )
