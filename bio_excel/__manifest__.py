# -*- coding: utf-8 -*-

{
    "name": 'Biosphera - Excel',
    "author": 'Biosphera',
    'version': '16.0.1.2.0',
    'description': 'Biosphera. Excel',
    'license': 'LGPL-3',
    'depends': ['account',
                'stock',
                'mrp_mps',
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
             'wizard/mrp_production_schedule_import_wizard_view.xml',
             ],
    'assets': {
        'web.assets_backend': [
            'bio_excel/static/src/xml/mrp_mps_control_panel_ext.xml',
            'bio_excel/static/src/js/mrp_mps_control_panel_patch.js',
        ],
    },
    'auto_install': False,
}
