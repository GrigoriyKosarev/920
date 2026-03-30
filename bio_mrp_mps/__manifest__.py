# -*- coding: utf-8 -*-

{
    "name": 'Biosphera - MPS',
    "author": 'Biosphera',
    'category': 'Manufacturing',
    'version': '16.0.1.0.0',
    'description': 'Biosphera. Master Production Schedule extensions',
    'license': 'LGPL-3',
    'depends': [
        'mrp_mps',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_mps_views.xml',
        'wizard/mrp_production_schedule_import_wizard_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'bio_mrp_mps/static/src/xml/mrp_mps_control_panel_ext.xml',
            'bio_mrp_mps/static/src/js/mrp_mps_control_panel_patch.js',
        ],
    },
    'auto_install': False,
}
