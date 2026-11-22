# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """Credit-control flag and the groups assigned to a customer."""

    _inherit = 'res.partner'

    credit_control = fields.Boolean(
        string='Credit Control',
        help='When enabled, sales orders are checked against the credit groups '
             'of this customer for the selected sales channel.',
    )
    credit_group_ids = fields.Many2many(
        comodel_name='sale.credit.group',
        relation='sale_credit_group_partner_rel',
        column1='partner_id',
        column2='credit_group_id',
        string='Credit Groups',
    )

    @api.constrains('credit_control', 'credit_group_ids')
    def _check_credit_groups(self):
        """Require at least one group when credit control is enabled."""
        for partner in self:
            if partner.credit_control and not partner.credit_group_ids:
                raise ValidationError(_(
                    "Select at least one credit group for %(partner)s "
                    "when credit control is enabled.",
                    partner=partner.display_name,
                ))

    def _get_credit_control_partner(self):
        """Return the partner whose credit control applies to a sale.

        A contact can be configured on its own. Otherwise the commercial
        entity is used, which is where the flag is usually set.

        :return: Partner that should be evaluated.
        """
        self.ensure_one()
        if self.credit_control:
            return self
        commercial = self.commercial_partner_id
        if commercial and commercial.credit_control:
            return commercial
        return self
