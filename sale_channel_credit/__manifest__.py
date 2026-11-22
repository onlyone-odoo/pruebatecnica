# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    'name': 'Sales Channel Credit',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sales channels, delivery warehouse, invoice journal and credit groups',
    'author': 'Prueba técnica',
    'license': 'AGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
        'account',
        'mail',
    ],
    'data': [
        'data/ir_sequence_data.xml',
        'security/ir.model.access.csv',
        'security/credit_security.xml',
        'views/sale_channel_views.xml',
        'views/credit_group_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'report/credit_group_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
