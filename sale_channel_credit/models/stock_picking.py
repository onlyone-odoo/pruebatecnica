# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class StockPicking(models.Model):
    """Sales channel copied from the sales order onto the transfer."""

    _inherit = 'stock.picking'

    channel_id = fields.Many2one(
        comodel_name='sale.channel',
        string='Sales Channel',
        index=True,
        ondelete='restrict',
        copy=False,
        readonly=True,
    )


class StockMove(models.Model):
    """Put the sales channel on the picking created for a sale move."""

    _inherit = 'stock.move'

    def _get_new_picking_values(self):
        """Add the sales channel when every move comes from the same channel."""
        values = super()._get_new_picking_values()
        channels = self.sale_line_id.order_id.channel_id
        if len(channels) == 1:
            values['channel_id'] = channels.id
        return values
