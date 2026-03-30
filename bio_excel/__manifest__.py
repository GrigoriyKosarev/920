# -*- coding: utf-8 -*-

{
    "name": 'Biosphera - Excel',
    "author": 'Biosphera',
    'version': '16.0.1.3.0',
    'description': 'Biosphera. Excel',
    'license': 'LGPL-3',
    'depends': ['account',
                'stock',
                'product',
                ],
    'data': [
             'security/ir.model.access.csv',
             'security/res_groups.xml',
             'views/product_pricelist_views.xml',
             'views/stock_picking_views.xml',
             'wizard/export_bill_action.xml',
             'wizard/export_bill_wizard_views.xml',
             'wizard/pricelist_import_wizard_views.xml',
             ],
    'auto_install': False,
}
