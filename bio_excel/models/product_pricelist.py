from odoo import models, _


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def action_bio_upload_pricelist(self):
        """Open the pricelist import wizard"""
        return {
            'name': 'Upload Pricelist',
            'type': 'ir.actions.act_window',
            'res_model': 'pricelist.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_pricelist_id': self.id}
        }
